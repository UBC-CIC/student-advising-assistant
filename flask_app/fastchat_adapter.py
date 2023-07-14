from langchain.llms import BaseLLM
from langchain.callbacks.manager import CallbackManagerForLLMRun
from fastchat.model import get_conversation_template
from typing import Optional, List, Any

class FastChatLLM(BaseLLM):
    # Adapter to use any supported LLM with fastchat prompting tools
    # Adapted from https://github.com/lm-sys/FastChat/blob/main/fastchat/serve/huggingface_api.py

    base_llm: BaseLLM
    template: Any
    
    def __init__(self, base_llm: BaseLLM, model_name: str):
        """
        - base_llm: The langchain LLM model that will be called
        - model_name: The name of the model, used to get conversation templates from fastchat
             See https://github.com/lm-sys/FastChat/blob/main/fastchat/conversation.py for options
        """
        self.base_llm = base_llm
        self.template = get_conversation_template(model_name)

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """Run the LLM on the given prompt and input."""
        self.template.messages = []
        self.template.append_message(self.template.roles[0], prompt)
        self.template.append_message(self.template.roles[1], None)
        fastchat_prompt = self.template.get_prompt()
        result = self.base_llm.generate(fastchat_prompt, stop, run_manager, **kwargs)
        return result