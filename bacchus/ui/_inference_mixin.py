"""
Inference mixin for MainWindow.

Extracted from main_window.py. Contains all inference-related methods
including tool calling, permission checking, and generation lifecycle.
"""

import json
import logging
import re
from typing import Optional

from bacchus.config import load_settings, save_settings


logger = logging.getLogger(__name__)


def _describe_tool_call(tool_name: str, arguments: dict) -> tuple[str, str]:
    """Return (action_description, detail) for a tool call."""
    mapping = {
        "read_file":        ("read a file",        arguments.get("path", "")),
        "write_file":       ("write a file",       arguments.get("path", "")),
        "edit_file":        ("edit a file",        arguments.get("path", "")),
        "list_directory":   ("list a directory",   arguments.get("path", "")),
        "create_directory": ("create a directory", arguments.get("path", "")),
        "execute_command":  ("execute a command",  arguments.get("command", "")),
        "search_web":       ("search the web",     arguments.get("query", "")),
        "fetch_webpage":    ("fetch a webpage",    arguments.get("url", "")),
    }
    return mapping.get(tool_name, (f"use tool '{tool_name}'", str(arguments)))


class InferenceMixin:
    """
    Mixin providing inference lifecycle methods for MainWindow.

    Requires self to have:
        - self.database (Database)
        - self.model_manager (ModelManager or None)
        - self.mcp_manager (MCPManager or None)
        - self.chat_widget (ChatWidget)
        - self.prompt_area (PromptArea)
        - self.status_bar_widget (StatusBar)
        - self._current_conversation_id (Optional[int])
        - self._inference_worker (Optional[QThread])
        - self._current_response (str)
        - self._inference_conversation_id (Optional[int])
        - self._tool_iteration_count (int)
        - self._max_tool_iterations (int)
        - self._seen_tool_calls (set)
        - self._in_response_phase (bool)
        - self._in_argument_phase (bool)
        - self._pending_tool_name (str)
        - self._session_allowed_tools (set)
        - self._settings (dict)
    """

    _SAFE_TOOLS = {"search_web", "fetch_webpage", "read_file", "list_directory"}
    _RISKY_TOOLS = {"write_file", "edit_file", "create_directory", "execute_command"}
    _POLICY_DEFAULTS = {
        "search_web": "always_allow",
        "fetch_webpage": "always_allow",
    }

    def _start_inference(self, conversation):
        """
        Start inference for the current conversation.

        Args:
            conversation: Conversation dataclass
        """
        from bacchus.inference.chat import (
            construct_prompt,
            trim_context_fifo,
            estimate_tokens
        )
        from bacchus.inference.inference_worker import InferenceWorker

        # Get conversation messages
        messages = self.database.get_conversation_messages(self._current_conversation_id)

        # Convert to format expected by inference
        formatted_messages = [
            {
                "role": msg.role,
                "content": (
                    f"[Image: {msg.image_description}]\n{msg.content}"
                    if msg.image_description
                    else msg.content
                )
            }
            for msg in messages
        ]

        # Get system message from dynamic prompt manager
        from bacchus.prompts import get_prompt_manager

        prompt_manager = get_prompt_manager()
        system_message = prompt_manager.get_system_prompt(self.mcp_manager)

        logger.debug(f"Loaded dynamic system prompt ({len(system_message)} chars)")

        # Inject project custom prompt if conversation belongs to a project
        conv = self.database.get_conversation(self._current_conversation_id)
        if conv and conv.project_id:
            project = self.database.get_project(conv.project_id)
            if project and project.custom_prompt:
                system_message = system_message + "\n\n" + project.custom_prompt
                logger.debug(
                    f"Appended project custom prompt for project {conv.project_id} "
                    f"({len(project.custom_prompt)} chars)"
                )

        # Build RAG context if document is attached and embeddings exist
        rag_context, document_name = self._build_rag_context(formatted_messages)

        # Get context window from model manager
        model_folder = self.model_manager.get_current_chat_model()
        context_window = self.model_manager.get_context_window()

        # Trim context if needed
        system_tokens = estimate_tokens(system_message)
        rag_tokens = estimate_tokens(rag_context) if rag_context else 0

        logger.info(
            f"Context window: {context_window} tokens | "
            f"model={model_folder} | "
            f"history={len(formatted_messages)} messages"
        )

        trimmed_messages = trim_context_fifo(
            formatted_messages,
            max_tokens=context_window,
            system_tokens=system_tokens,
            rag_tokens=rag_tokens
        )

        # Construct prompt
        prompt = construct_prompt(
            messages=trimmed_messages,
            system_message=system_message,
            rag_context=rag_context,
            document_name=document_name,
            model_folder=model_folder
        )

        logger.debug(f"Prompt constructed, length: {len(prompt)} chars")

        # Get LLM pipeline
        llm_pipeline = self.model_manager.get_llm_pipeline()

        # Calculate max_new_tokens
        estimated_used = system_tokens + sum(
            estimate_tokens(m.get("content", "")) for m in trimmed_messages
        )
        max_new_tokens = context_window - estimated_used - 512
        max_new_tokens = max(512, max_new_tokens)

        # Read generation parameters fresh from disk
        from bacchus.constants import DEFAULT_TEMPERATURE, DEFAULT_MIN_NEW_TOKENS
        _gen_settings = load_settings().get("generation", {})
        _temperature = _gen_settings.get("temperature", DEFAULT_TEMPERATURE)
        _min_new_tokens = _gen_settings.get("min_new_tokens", DEFAULT_MIN_NEW_TOKENS)

        # VLM path
        if self.model_manager.is_vl_pipeline_loaded():
            from bacchus.inference.vlm_worker import VLMInferenceWorker

            vlm_pipeline = self.model_manager.get_vlm_pipeline()

            _ACTION_MAX_TOKENS = 256
            _FILE_WRITE_TOOLS = {"write_file", "edit_file"}
            _FILE_ARG_TOKENS = 16384
            _DEFAULT_ARG_TOKENS = 2048

            vlm_generation_config = None
            last_msg = messages[-1] if messages else None
            if self._in_response_phase:
                vlm_generation_config = None
                logger.info("VLM response phase: plain streaming generation")
            elif self._in_argument_phase:
                from bacchus.inference.decision_schema import create_arguments_config
                arg_tokens = (
                    _FILE_ARG_TOKENS if self._pending_tool_name in _FILE_WRITE_TOOLS
                    else _DEFAULT_ARG_TOKENS
                )
                tool_schema = self._get_tool_schema(self._pending_tool_name)
                vlm_generation_config = create_arguments_config(
                    max_tokens=min(arg_tokens, max_new_tokens),
                    tool_schema=tool_schema,
                )
                logger.info(
                    f"VLM argument phase for '{self._pending_tool_name}' "
                    f"(max_tokens={min(arg_tokens, max_new_tokens)}, "
                    f"schema={'tool' if tool_schema else 'generic'})"
                )
            elif last_msg and last_msg.role in ("user", "system"):
                is_last_iteration = self._tool_iteration_count >= self._max_tool_iterations - 1
                if not is_last_iteration:
                    from bacchus.inference.decision_schema import create_action_config

                    tool_names = []
                    if self.mcp_manager:
                        for server in self.mcp_manager.list_servers():
                            if server.status == "running" and server.client:
                                for tool in server.client._tools:
                                    tool_names.append(tool.name)

                    if tool_names:
                        vlm_generation_config = create_action_config(
                            tool_names, max_tokens=min(_ACTION_MAX_TOKENS, max_new_tokens)
                        )
                        logger.info(
                            f"VLM action phase with {len(tool_names)} tools "
                            f"(iteration {self._tool_iteration_count + 1}/{self._max_tool_iterations})"
                        )
                    else:
                        logger.info("No tools available for VLM, using plain generation")
                else:
                    vlm_generation_config = None
                    logger.info("VLM final iteration: forcing plain generation for summary")

            self._inference_worker = VLMInferenceWorker(
                vlm_pipeline=vlm_pipeline,
                system_message=system_message,
                messages=messages,
                max_tokens=max_new_tokens,
                temperature=_temperature,
                min_new_tokens=_min_new_tokens if self._in_response_phase else 0,
                generation_config=vlm_generation_config,
                streaming=self._in_response_phase,
            )

            vlm_system_tokens = estimate_tokens(system_message)
            vlm_history_tokens = sum(estimate_tokens(m.content or "") + 4 for m in messages)
            vlm_total = vlm_system_tokens + vlm_history_tokens
            images_in_history = sum(1 for m in messages if m.image_path)
            logger.info(
                f"VLM context: {context_window} window | "
                f"system={vlm_system_tokens} history={vlm_history_tokens} "
                f"({len(messages)} messages, {images_in_history} with images) | "
                f"estimate={vlm_total} ({100 * vlm_total / context_window:.1f}%) | "
                f"response_budget={max_new_tokens}"
            )

            self._current_response = ""
            self._inference_conversation_id = self._current_conversation_id

            self._inference_worker.image_described.connect(self._on_image_described)
            self._inference_worker.token_generated.connect(self._on_token_generated)
            self._inference_worker.generation_completed.connect(self._on_generation_completed)
            self._inference_worker.generation_failed.connect(self._on_generation_failed)
            self._inference_worker.start()
            logger.info(
                f"VLM inference worker started "
                f"(max_tokens={max_new_tokens}, streaming={self._in_response_phase})"
            )
            return

        _ACTION_MAX_TOKENS = 256
        _FILE_WRITE_TOOLS = {"write_file", "edit_file"}
        _FILE_ARG_TOKENS = 16384
        _DEFAULT_ARG_TOKENS = 2048

        generation_config = None
        last_message = formatted_messages[-1] if formatted_messages else None

        if self._in_response_phase:
            generation_config = None  # Plain streaming
        elif self._in_argument_phase:
            from bacchus.inference.decision_schema import create_arguments_config
            arg_tokens = (
                _FILE_ARG_TOKENS if self._pending_tool_name in _FILE_WRITE_TOOLS
                else _DEFAULT_ARG_TOKENS
            )
            tool_schema = self._get_tool_schema(self._pending_tool_name)
            generation_config = create_arguments_config(
                max_tokens=min(arg_tokens, max_new_tokens),
                tool_schema=tool_schema,
            )
            logger.info(
                f"LLM argument phase for '{self._pending_tool_name}' "
                f"(max_tokens={min(arg_tokens, max_new_tokens)}, "
                f"schema={'tool' if tool_schema else 'generic'})"
            )
        elif last_message and last_message["role"] in ("user", "system"):
            is_last_iteration = self._tool_iteration_count >= self._max_tool_iterations - 1
            if not is_last_iteration:
                from bacchus.inference.decision_schema import create_action_config

                tool_names = []
                if self.mcp_manager:
                    for server in self.mcp_manager.list_servers():
                        if server.status == "running" and server.client:
                            for tool in server.client._tools:
                                tool_names.append(tool.name)

                if tool_names:
                    generation_config = create_action_config(
                        tool_names, max_tokens=min(_ACTION_MAX_TOKENS, max_new_tokens)
                    )
                    logger.info(
                        f"LLM action phase with {len(tool_names)} tools "
                        f"(iteration {self._tool_iteration_count + 1}/{self._max_tool_iterations})"
                    )
                else:
                    logger.info("No tools available, using plain generation")
            else:
                generation_config = None
                logger.info(
                    f"Final iteration ({self._max_tool_iterations}): "
                    "forcing plain generation for summary"
                )

        self._inference_worker = InferenceWorker(
            llm_pipeline=llm_pipeline,
            prompt=prompt,
            max_tokens=max_new_tokens,
            temperature=_temperature,
            min_new_tokens=_min_new_tokens if self._in_response_phase else 0,
            generation_config=generation_config
        )

        if generation_config:
            logger.info(
                f"Starting STRUCTURED generation with decision schema "
                f"(max_tokens={max_new_tokens})"
            )
        else:
            logger.info(
                f"Starting generation with max_tokens={max_new_tokens} "
                f"(context_window={context_window})"
            )

        self._current_response = ""
        self._inference_conversation_id = self._current_conversation_id

        self._inference_worker.token_generated.connect(self._on_token_generated)
        self._inference_worker.generation_completed.connect(self._on_generation_completed)
        self._inference_worker.generation_failed.connect(self._on_generation_failed)

        self._inference_worker.start()
        logger.info("Inference worker started")

    def _on_image_described(self, message_id: int, description: str) -> None:
        """Store auto-generated image description produced by VLMInferenceWorker."""
        try:
            self.database.update_message_image_description(message_id, description)
            logger.info(
                f"Stored image description for message {message_id} ({len(description)} chars)"
            )
        except Exception as e:
            logger.warning(f"Failed to store image description for message {message_id}: {e}")

    def _on_token_generated(self, token: str):
        """Handle token generation (streaming) — update the live bubble in the chat widget."""
        self._current_response += token
        if self._current_conversation_id == self._inference_conversation_id:
            self.chat_widget.append_streaming_token(token)

    def _strip_thinking_tags(self, response: str) -> str:
        """
        Strip <think>...</think> tags from reasoning model responses.

        DeepSeek R1 and similar models output their reasoning process in think tags.
        We remove these for cleaner display while keeping the final answer.
        """
        cleaned = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned.strip())
        return cleaned

    def _finalize_response(self, response: str) -> None:
        """Save the final assistant response to the DB and update the UI."""
        self._tool_iteration_count = 0
        self._seen_tool_calls = set()
        self._in_response_phase = False
        self._in_argument_phase = False
        self._pending_tool_name = ""

        if self._inference_conversation_id is not None:
            self.database.add_message(
                conversation_id=self._inference_conversation_id,
                role="assistant",
                content=response
            )
        else:
            logger.warning("No conversation ID captured for inference - response not saved")

        if self._current_conversation_id == self._inference_conversation_id:
            self.chat_widget.load_conversation(self._current_conversation_id)
        else:
            self.sidebar.refresh_conversations()

        self.prompt_area.set_generating(False)
        self.status_bar_widget.set_active(False)

        if self._inference_worker:
            self._inference_worker.deleteLater()
            self._inference_worker = None
        self._current_response = ""

        logger.info("Generation cycle complete")

    def _on_generation_completed(self, response: str):
        """Handle generation completion and autonomous tool execution."""
        logger.info(f"Generation completed, length: {len(response)} chars")

        if self.model_manager:
            model_folder = self.model_manager.get_current_chat_model() or ""
            if "deepseek" in model_folder.lower() or "r1" in model_folder.lower():
                original_len = len(response)
                response = self._strip_thinking_tags(response)
                if len(response) < original_len:
                    logger.info(f"Stripped thinking tags, {original_len} -> {len(response)} chars")

        if self._in_response_phase:
            logger.info("Response phase complete — finalizing")
            self._finalize_response(response)
            return

        from bacchus.inference.autonomous_tools import execute_tool_call, format_tool_result, ToolCall

        if self._in_argument_phase:
            self._in_argument_phase = False
            tool_name = self._pending_tool_name
            self._pending_tool_name = ""
            try:
                arguments = json.loads(response.strip())
                if not isinstance(arguments, dict):
                    raise ValueError("arguments must be a JSON object")
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Failed to parse tool arguments: {e} — raw: {response[:200]}")
                self._finalize_response("[Error: could not parse tool arguments.]")
                return
            logger.info(f"Argument phase complete: {tool_name}({list(arguments.keys())})")
            self._dispatch_tool_call(tool_name, arguments, response)
            return

        from bacchus.inference.decision_schema import parse_action
        action = parse_action(response)

        if action["action"] == "tool_call" and self._tool_iteration_count < self._max_tool_iterations:
            tool_name = action["tool"]
            logger.info(f"Action phase: tool_call={tool_name} — starting argument phase")
            if self._inference_worker:
                self._inference_worker.deleteLater()
                self._inference_worker = None
            self._in_argument_phase = True
            self._pending_tool_name = tool_name
            conversation = self.database.get_conversation(self._inference_conversation_id)
            if conversation:
                self._start_inference(conversation)
                return
            logger.error("Could not get conversation for argument phase")
            self._finalize_response("[Error: could not start argument generation.]")
            return

        if action["action"] == "tool_call" and self._tool_iteration_count >= self._max_tool_iterations:
            logger.warning(f"Max tool iterations ({self._max_tool_iterations}) reached")
            self._finalize_response(
                "[System: Maximum tool iterations reached. Response may be incomplete.]"
            )
            return

        if action["action"] == "respond":
            logger.info("Action phase: respond — starting streaming response phase")
            if self._inference_worker:
                self._inference_worker.deleteLater()
                self._inference_worker = None
            self._in_response_phase = True
            if self._current_conversation_id == self._inference_conversation_id:
                self.chat_widget.begin_streaming()
            conversation = self.database.get_conversation(self._inference_conversation_id)
            if conversation:
                self._start_inference(conversation)
                return
            logger.warning("Could not restart inference for response phase — no conversation")
            self._in_response_phase = False
        return

    def _dispatch_tool_call(self, tool_name: str, arguments: dict, raw_text: str) -> None:
        """Execute a tool call (after arguments have been generated) and continue the loop."""
        from bacchus.inference.autonomous_tools import execute_tool_call, format_tool_result, ToolCall

        import hashlib
        call_key = (
            tool_name,
            hashlib.md5(json.dumps(arguments, sort_keys=True).encode()).hexdigest()
        )
        if call_key in self._seen_tool_calls:
            logger.warning(f"Duplicate tool call: {tool_name} — forcing response phase")
            if self._inference_worker:
                self._inference_worker.deleteLater()
                self._inference_worker = None
            self._in_response_phase = True
            if self._current_conversation_id == self._inference_conversation_id:
                self.chat_widget.begin_streaming()
            conversation = self.database.get_conversation(self._inference_conversation_id)
            if conversation:
                self._start_inference(conversation)
            return
        self._seen_tool_calls.add(call_key)
        self._tool_iteration_count += 1

        tool_call = ToolCall(tool_name=tool_name, arguments=arguments, raw_text=raw_text)

        tool_json = json.dumps({"tool": tool_name, "arguments": arguments}, indent=2)
        if self._inference_conversation_id is not None:
            self.database.add_message(
                conversation_id=self._inference_conversation_id,
                role="assistant",
                content=tool_json,
                mcp_calls=[{"tool": tool_name, "params": arguments}]
            )

        if not self.mcp_manager:
            logger.warning("No MCP manager — cannot execute tool")
            self._finalize_response(f"[Tool {tool_name} could not be executed: no MCP manager.]")
            return

        permission = self._check_tool_permission(tool_name, arguments)

        if permission == "deny":
            deny_msg = f"Permission denied by user for {tool_name}."
            formatted_result = format_tool_result(tool_name, False, deny_msg)
            if self._inference_conversation_id is not None:
                self.database.add_message(
                    conversation_id=self._inference_conversation_id,
                    role="system",
                    content=formatted_result,
                    mcp_calls=[{"tool": tool_name, "params": arguments,
                                "result": deny_msg, "success": False}]
                )
            if self._current_conversation_id == self._inference_conversation_id:
                self.chat_widget.load_conversation(self._current_conversation_id)
            if self._inference_worker:
                self._inference_worker.deleteLater()
                self._inference_worker = None
            conversation = self.database.get_conversation(self._inference_conversation_id)
            if conversation:
                self._start_inference(conversation)
            return

        if permission == "sandbox":
            from bacchus.sandbox.runner import SandboxRunner
            from bacchus.constants import SANDBOX_DIR
            runner = SandboxRunner(SANDBOX_DIR)
            if tool_name == "execute_command":
                success, result = runner.run_command(arguments.get("command", ""))
            elif tool_name in ("write_file", "edit_file", "create_directory"):
                sandboxed_args = dict(arguments)
                if "path" in sandboxed_args:
                    sandboxed_args["path"] = runner.sandbox_path(sandboxed_args["path"])
                self.mcp_manager.ensure_path_allowed("filesystem", str(SANDBOX_DIR), persist=False)
                sandboxed_call = ToolCall(
                    tool_name=tool_name, arguments=sandboxed_args, raw_text=raw_text
                )
                success, result = execute_tool_call(sandboxed_call, self.mcp_manager)
            else:
                success, result = execute_tool_call(tool_call, self.mcp_manager)
            formatted_result = format_tool_result(tool_name, success, f"[SANDBOXED] {result}")
        else:
            success, result = execute_tool_call(tool_call, self.mcp_manager)
            logger.info(f"Tool '{tool_name}' {'succeeded' if success else 'failed'}, {len(result)} chars")
            formatted_result = format_tool_result(tool_name, success, result)

        if self._inference_conversation_id is not None:
            self.database.add_message(
                conversation_id=self._inference_conversation_id,
                role="system",
                content=formatted_result,
                mcp_calls=[{"tool": tool_name, "params": arguments,
                            "result": result, "success": success}]
            )

        if self._current_conversation_id == self._inference_conversation_id:
            self.chat_widget.load_conversation(self._current_conversation_id)

        if self._inference_worker:
            self._inference_worker.deleteLater()
            self._inference_worker = None

        conversation = self.database.get_conversation(self._inference_conversation_id)
        if conversation:
            self._start_inference(conversation)
            return
        logger.error(
            f"Failed to get conversation {self._inference_conversation_id} for next iteration"
        )

    def _get_tool_schema(self, tool_name: str) -> Optional[dict]:
        """Return the MCP inputSchema for *tool_name*, or None if not found."""
        if not self.mcp_manager:
            return None
        for server in self.mcp_manager.list_servers():
            if server.status == "running" and server.client:
                for tool in server.client._tools:
                    if tool.name == tool_name:
                        return tool.parameters or None
        return None

    def _check_tool_permission(self, tool_name: str, arguments: dict) -> str:
        """
        Check if a tool action is permitted, asking the user if not.

        Returns 'allow', 'sandbox', or 'deny'.
        """
        from bacchus.ui.permission_dialog import (
            ask_permission, ALLOW_ALWAYS, ALLOW_SESSION, SANDBOX, DENY, ALLOW_ONCE
        )

        if tool_name in self._session_allowed_tools:
            return "allow"

        settings = load_settings()
        policy = (
            settings.get("permissions", {})
            .get("tool_policy", {})
            .get(tool_name, self._POLICY_DEFAULTS.get(tool_name, "ask"))
        )

        if policy == "always_allow":
            return "allow"
        if policy == "always_deny":
            return "deny"
        if policy == "sandbox_always":
            return "sandbox"

        risky = tool_name not in self._SAFE_TOOLS
        action_desc, detail = _describe_tool_call(tool_name, arguments)
        result = ask_permission(tool_name, action_desc, detail, self, risky=risky)

        if result == DENY:
            return "deny"
        if result == SANDBOX:
            return "sandbox"

        persist_path = (result == ALLOW_ALWAYS)

        if result == ALLOW_SESSION:
            self._session_allowed_tools.add(tool_name)
        elif result == ALLOW_ALWAYS:
            s = load_settings()
            s.setdefault("permissions", {}).setdefault("tool_policy", {})[tool_name] = "always_allow"
            save_settings(s)

        if tool_name in ("read_file", "write_file", "edit_file",
                         "list_directory", "create_directory") and self.mcp_manager:
            import os
            from pathlib import Path as _P
            raw_path = arguments.get("path", "")
            if raw_path:
                try:
                    resolved = _P(os.path.expandvars(raw_path)).resolve()
                    parent = str(resolved.parent if tool_name != "list_directory"
                                 else resolved)
                    self.mcp_manager.ensure_path_allowed(
                        "filesystem", parent, persist=persist_path
                    )
                except Exception as e:
                    logger.warning(f"Could not expand allowed_paths for {raw_path}: {e}")

        return "allow"

    def _on_generation_failed(self, error: str):
        """Handle generation failure."""
        logger.error(f"Generation failed: {error}")

        from bacchus import locales
        self.prompt_area.set_generating(False)
        self.status_bar_widget.set_active(False)

        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(
            self,
            locales.get_string("error.generation_failed", "Generation Failed"),
            locales.get_string("error.generation_failed_msg",
                f"Failed to generate response: {error}")
        )

        if self._inference_worker:
            self._inference_worker.deleteLater()
            self._inference_worker = None
        self._current_response = ""
