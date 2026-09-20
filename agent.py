"""
The agent loop: the model decides when to call get_sales_order, we
run it, and feed the result back until the model has a final answer.
"""
import json
import os
from openai import OpenAI
from tools import get_sales_order, get_full_order_details

# --- Model provider: swap these three lines, nothing else, to change engine ---
# Default: Ollama, running locally, free forever, no key of any kind.
#client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
#MODEL = "llama3.2" 
#MODEL = "ollama launch claude"

# Section 07 (deploy) swaps in the hosted, free-tier Gemini instead, because
# a deployed app can't reach Ollama on your laptop:
client = OpenAI(
       base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
       api_key=os.environ.get("GEMINI_API_KEY"),
)
MODEL = "gemini-3.6-flash"   # check ai.google.dev for the current name
# -------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_sales_order",
            "description": "Look up one SAP sales order by its ID and return its type, customer, value and status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sales_order_id": {
                        "type": "string",
                        "description": "The SAP sales order number, e.g. '1234' or '5000000000'.",
                    }
                },
                "required": ["sales_order_id"],
            },
        },

            
        "type": "function",
        "function": {
            "name": "get_full_order_details",
            "description": "Get the line items, partners (sold-to/ship-to/bill-to/payer), and related documents (deliveries, invoices, quotations) for one SAP sales order.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sales_order_id": {
                        "type": "string",
                        "description": "The SAP sales order number, e.g. '1234' or '5000000000'.",
                    }
                },
                "required": ["sales_order_id"],
            },
        },
    },
    
]

SYSTEM_PROMPT = (
    "You are an SAP Order Status Agent for an Accounts Receivable team. "
    "Use get_sales_order for questions about an order's status, type, "
    "customer or value. Use get_full_order_details for questions about "
    "what's IN an order (line items, materials, quantities), who's "
    "involved (partners), or what other documents are linked to it "
    "(related objects such as deliveries or invoices) — call both tools "
    "if a question needs both. "
    "Partner records use short SAP codes: AG = sold-to party, "
    "WE = ship-to party, RE = bill-to party, RG = payer. Translate these "
    "to plain English in your answer, never show the raw code. "
    "If a lookup returns found: false with NO error field, the order (or "
    "the data asked for) genuinely doesn't exist — say so plainly, don't "
    "guess. If a lookup returns found: false WITH an error field, that's a "
    "technical problem (e.g. SAP rejected the key, or was unreachable), "
    "not a missing order — tell the user there was a problem checking SAP "
    "right now, briefly mention what went wrong, and suggest trying again "
    "shortly. A result with a non-null 'warnings' field succeeded overall "
    "but one part of it had a technical hiccup — mention that part "
    "briefly, but still answer from the data that did come back. Never "
    "present a technical error as if the order simply wasn't found. Keep "
    "answers short and business-friendly, never raw JSON."
)


def run_tool(name: str, arguments: dict) -> dict:
    if name == "get_sales_order":
        return get_sales_order(arguments["sales_order_id"])
    if name == "get_full_order_details":
        return get_full_order_details(arguments["sales_order_id"])
    raise ValueError(f"Unknown tool: {name}")


def ask_agent(user_message: str, history: list) -> tuple[str, list]:
    """Send one user turn through the agent loop, returning (answer, new_history)."""
    messages = history + [{"role": "user", "content": user_message}]
    if not any(m.get("role") == "system" for m in messages):
        messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})

    while True:
        response = client.chat.completions.create(
            model=MODEL,
            tools=TOOLS,
            messages=messages,
        )
        #print("Model that actually answered:", response.model)
        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))

        if not message.tool_calls:
            return message.content or "", messages

        for call in message.tool_calls:
            args = json.loads(call.function.arguments)
            result = run_tool(call.function.name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result),
            })


if __name__ == "__main__":
    print("Order Status Agent — ask about a sales order (Ctrl+C to quit)\n")
    chat_history: list = []
    while True:
        question = input("You: ")
        answer, chat_history = ask_agent(question, chat_history)
        print(f"Agent: {answer}\n")