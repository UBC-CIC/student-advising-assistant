from langchain.llms.base import BaseLLM, LLM
from langchain.callbacks.manager import CallbackManagerForLLMRun
from fastchat.model import get_conversation_template
from typing import Optional, List, Any

default_system_instruction = """
A chat between a University of British Columbia (UBC) student and an artificial intelligence assistant. 
The assistant gives helpful, detailed, and polite answers to the user's questions."""

class FastChatLLM(LLM):
    # Adapter to use any supported LLM with fastchat prompting tools
    # Adapted from https://github.com/lm-sys/FastChat/blob/main/fastchat/serve/huggingface_api.py

    base_llm: BaseLLM
    template: Any
    llm_type: str = 'fastchat-adapter'
    
    @classmethod
    def from_base_llm(cls, base_llm: BaseLLM, model_name: str, system_instruction:str = None):
        """
        - base_llm: The langchain LLM model that will be called
        - model_name: The name of the base llm, used to get conversation templates from fastchat
             See https://github.com/lm-sys/FastChat/blob/main/fastchat/conversation.py for options
        """
        template=get_conversation_template(model_name)
        if system_instruction:
            template.system = system_instruction
        else:
            template.system = default_system_instruction
        return cls(base_llm=base_llm, template=template)

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
        result = self.base_llm.generate([fastchat_prompt], stop, run_manager, **kwargs)
        
        output = result.generations[0][0].text
        if output.startswith(fastchat_prompt): 
            # If the model returned the prompt as well as generated text, remove the prompt
            output = output[len(fastchat_prompt):]
            
        return output
    
    def _llm_type(self) -> str:
        """Return type of llm."""
        return self.llm_type