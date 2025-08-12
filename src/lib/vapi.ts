// vapi.ts - Web SDK for front-end events/voice
import Vapi from "@vapi-ai/web";

// Uses your NEXT_PUBLIC_VAPI_API_KEY from .env
export const vapi = new Vapi(process.env.NEXT_PUBLIC_VAPI_API_KEY!);
