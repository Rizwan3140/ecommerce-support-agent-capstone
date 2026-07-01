# Technical Report: E-Commerce Customer Support Assistant

## 1. Problem Scope and Assumptions

E-commerce support teams repeatedly answer questions about order status,
returns, refunds, payments, shipping, product details, and policy exceptions.
This prototype automates common support flows while escalating uncertain or
unsupported cases to a human agent.

Supported issue types:

- Orders and tracking
- Returns, replacements, and refunds
- Shipping fees and delivery delays
- Payment failures and reversal timelines
- Product specification questions
- General FAQ and policy questions

Assumptions:

- Customer data is synthetic.
- Mock backend tools stand in for real OMS, returns, refund, and product catalog
  APIs.
- Policies are sample/capstone documents and should not be treated as legal
  advice.
- A Groq API key is used for LLM stages. HuggingFace embeddings and FAISS are
  used for retrieval.

## 2. Architecture

The assistant combines RAG, mock backend tools, and a multi-step agent flow.

1. User submits a support ticket and optional order context through Streamlit or
   `POST /query`.
2. Mock tools run when relevant:
   - `get_order_status(order_id)`
   - `create_return_request(order_id, reason)`
   - `get_refund_policy()`
   - `search_products(query)`
3. The triage agent classifies the issue into `refund`, `shipping`, `payment`,
   `promo`, `fraud`, or `other`.
4. The retriever searches a FAISS index built from `data/policies/`, including
   the supplied sample FAQ, policy, and product catalog facts.
5. The writer agent drafts a policy-grounded response using retrieved text and
   backend facts.
6. The compliance agent validates citations and escalates unsupported answers.
7. The API returns structured JSON with decision, rationale, citations,
   customer response, internal notes, and tool results.

## 3. Data Pipeline

Knowledge base sources:

- Upstream synthetic policy corpus in `data/policies/*.txt`
- Capstone sample FAQ in `data/policies/capstone_sample_faq.md`
- Capstone sample policies in `data/policies/capstone_sample_policies.md`
- Product catalog facts in `data/policies/capstone_product_catalog.md`

Ingestion:

- Load `.txt` and `.md` files.
- Normalize whitespace.
- Split into overlapping chunks.
- Embed chunks with `sentence-transformers/all-MiniLM-L6-v2`.
- Persist FAISS index under `data/faiss_index/`.

## 4. Prompt and Agent Design

Triage prompt:

- Produces a strict JSON classification.
- Asks at most three clarifying questions.
- Avoids asking for facts already present in ticket or context.

Writer prompt:

- Uses retrieved policy context as the source of truth for policy decisions.
- Uses mock tool output only as order/product facts.
- Requires citations from retrieved chunk IDs for approve, deny, or partial
  decisions.
- Escalates when evidence is missing.

Compliance prompt:

- Checks that citations are valid.
- Rejects unsupported policy promises.
- Rewrites minor wording issues or escalates major evidence failures.

## 5. Mock Tool Design

Implemented in `tools/mock_apis.py`.

| Tool | Purpose |
|---|---|
| `get_order_status(order_id)` | Looks up mock OMS status, tracking, delivery, payment, and product data. |
| `create_return_request(order_id, reason)` | Creates a synthetic RMA if the delivered order is roughly eligible. |
| `get_refund_policy()` | Returns the sample refund window and refund timeline. |
| `search_products(query)` | Searches the supplied product catalog for specs such as HDMI or Bluetooth. |

The same functions are exposed through FastAPI endpoints:

- `GET /tools/order-status/{order_id}`
- `POST /tools/returns`
- `GET /tools/refund-policy`
- `GET /tools/products?q=...`

## 6. Conversation Flows

Order tracking:

- If order ID exists, call order status tool and answer with status/tracking.
- If missing, ask for order ID.

Return/refund:

- Call order status.
- Call return request when order ID is present.
- Retrieve return/refund policy.
- Approve, deny, partial, needs_info, or escalate based on evidence.

Payment failure:

- Retrieve payment/refund policy.
- Explain reversal timeline.
- Ask for transaction reference if required.

Product specs:

- Search product catalog.
- Answer from product facts and RAG catalog document.

Fallback:

- If information is missing, use `needs_info`.
- If retrieved policy is weak or citations fail, use `escalate`.

## 7. Evaluation Method

The repo includes `evaluation/test_cases.json` with 20 test cases spanning
normal, exception, conflict, and not-policy cases. The runner measures:

- Citation coverage
- Unsupported-claim proxy
- Escalation correctness
- Per-case classifications and decisions

The supplied capstone dataset also includes labeled example intents in
`customer_queries_sample.csv`; those are reflected in
`evaluation/capstone_queries.csv`.

## 8. Safety and Ethics

Safety measures:

- Policy-grounded answers with citations.
- Compliance pass before final response.
- Escalation when evidence is missing or conflicting.
- No request for full card number, CVV, passwords, or unnecessary sensitive
  data.
- Privacy policy included in RAG corpus.

Known limitations:

- Mock tools are deterministic and not connected to a real database.
- LLM output can still vary across runs.
- Evaluation is small and synthetic.
- Real production use would need legal review, PII redaction, authentication,
  audit logs, and human QA.

## 9. Future Improvements

- Add real authentication and customer-specific order lookup.
- Add persistent return-ticket storage.
- Add hybrid retrieval and reranking.
- Add automatic PII detection/redaction.
- Expand evaluation with more edge cases and human scoring.
- Add dashboard analytics for unresolved/escalated cases.

