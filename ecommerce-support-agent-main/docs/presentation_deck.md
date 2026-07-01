# Presentation Deck Outline

## Slide 1: Title

E-Commerce Customer Support Assistant

AI assistant for order, return, refund, payment, shipping, and product support.

## Slide 2: Problem

Support teams receive repeated questions that are slow and costly to answer
manually. Plain LLMs can hallucinate policy details, so answers must be grounded
in official documents and checked before release.

## Slide 3: User Persona

Primary user: online shopper who wants fast help with an order, return, refund,
payment issue, or product question.

Secondary user: support team that needs consistent, policy-safe draft responses.

## Slide 4: Use Cases

- Where is my order?
- How do I return a product?
- My payment failed but money was deducted.
- What are shipping charges?
- Does this monitor have HDMI?
- I received a damaged or wrong item.

## Slide 5: System Architecture

User query -> mock tools -> triage agent -> FAISS retriever -> writer agent ->
compliance agent -> structured response.

Core components:

- FastAPI backend
- Streamlit UI
- Groq LLM
- HuggingFace embeddings
- FAISS vector store
- Mock OMS/returns/refund/catalog tools

## Slide 6: RAG Pipeline

Documents:

- Sample FAQ
- Sample policies
- Product catalog facts
- Expanded synthetic policy corpus

Pipeline:

Load documents -> clean -> chunk -> embed -> FAISS index -> retrieve top-k
policy chunks with citation IDs.

## Slide 7: Tool Calling

Mock tools:

- `get_order_status(order_id)`
- `create_return_request(order_id, reason)`
- `get_refund_policy()`
- `search_products(query)`

Tool results are shown in the final JSON and Streamlit UI.

## Slide 8: Conversation Flow

Example: "Where is my order #1002?"

1. Extract order ID.
2. Call order status tool.
3. Retrieve shipping/order policy.
4. Generate response with tracking ID and delivery estimate.
5. Include tool result in JSON.

## Slide 9: Guardrails

- Use retrieved policy text for policy decisions.
- Cite policy chunks.
- Escalate when evidence is weak.
- Ask clarifying questions only when required.
- Avoid sensitive payment data collection.

## Slide 10: Evaluation

Evaluation set covers:

- Normal cases
- Exceptions
- Conflicts
- Out-of-policy questions

Metrics:

- Citation coverage
- Unsupported claim proxy
- Escalation correctness
- Classification/decision inspection

## Slide 11: Demo Flow

1. Start backend.
2. Run `/ingest`.
3. Open Streamlit UI.
4. Try:
   - "Where is my order #1002?"
   - "I want to return order #1001."
   - "My payment failed but money was deducted."
   - "Does the 24-inch monitor have HDMI?"

## Slide 12: Limitations and Roadmap

Limitations:

- Mock data only
- Small synthetic evaluation
- Requires API key

Roadmap:

- Real order database
- Persistent ticket logs
- PII redaction
- More evaluation cases
- Human handoff queue

