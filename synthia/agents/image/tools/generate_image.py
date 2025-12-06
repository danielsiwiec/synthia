import os
import uuid
from typing import Any

from claude_agent_sdk import tool
from google import genai

from synthia.agents.tools import error_response, success_response
from synthia.helpers.pubsub import pubsub
from synthia.service.models import ImageCreated


def create_generate_image_tool(thread_id: int):
    @tool(
        "generate-image",
        "Generate an image from a text prompt using Gemini.",
        {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The text prompt describing the image to generate",
                },
            },
            "required": ["prompt"],
        },
    )
    async def generate_image(args: dict[str, Any]) -> dict[str, Any]:
        try:
            prompt = args["prompt"]
            client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

            response = client.models.generate_content(
                model="gemini-2.5-flash-image",
                contents=[prompt],
            )

            filename = None

            if response.parts is not None:
                for part in response.parts:
                    if part.inline_data is not None:
                        image = part.as_image()
                        if image is not None:
                            filename = f"generated_image_{uuid.uuid4().hex[:8]}.png"
                            image.save(filename)

            if filename:
                await pubsub.publish(ImageCreated(thread_id=thread_id, filename=filename))
                return success_response("Image generated and already sent to the user.")
            else:
                return error_response("No image or text was generated")

        except Exception as error:
            return error_response(f"Error generating image: {error}")

    return generate_image
