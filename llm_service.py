from google import genai
from config import settings

class GeminiService:
    def __init__(self):
        if settings.gemini_api_key:
            self.client = genai.Client(api_key=settings.gemini_api_key)
            self.model_id = "gemini-2.0-flash"  # Fast and efficient
        else:
            self.client = None
            print("❌ Gemini API Key missing!")

    def get_response(self, user_text: str) -> str:
        if not self.client:
            return "I am sorry, my brain is offline."

        try:
            # Simple single-turn generation for now. 
            # For multi-turn, you can pass history.
            prompt = f"""
            You are a helpful voice assistant for Rupeek, a gold loan company.
            Keep your answers short (1-2 sentences) and conversational because you are speaking on the phone.
            Do not use emojis or bullet points.
            
            User said: "{user_text}"
            """
            
            response = self.client.models.generate_content(
                model=self.model_id, 
                contents=prompt
            )
            return response.text
        except Exception as e:
            print(f"Gemini Error: {e}")
            return "I am having trouble connecting to the server."

llm_client = GeminiService()
