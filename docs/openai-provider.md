# OpenAI provider configuration

The Graxia LLM adapter uses the official OpenAI API host only. Its API key is
sent to `https://api.openai.com/v1/chat/completions`; custom hosts and redirects
are rejected. The shared `OPENAI_BASE_URL` setting must remain the official
base URL when using this adapter.

Set these deployment values using the model ID enabled for the account and the
current USD-per-million-token prices applicable to that account:

```dotenv
LLM_PROVIDER=openai
OPENAI_CHAT_MODEL=<account-enabled-chat-model-id>
OPENAI_INPUT_PRICE_USD_PER_1M=<operator-supplied-input-rate>
OPENAI_OUTPUT_PRICE_USD_PER_1M=<operator-supplied-output-rate>
```

Provide `OPENAI_API_KEY` through the deployment's secret store. Do not commit
the key or place it in this document. The model and both positive rates are
required for readiness and cost checks; this document intentionally supplies
no model ID or price. Confirm the model's availability and published prices in
the account before configuring them. Missing, zero, or invalid rates keep the
provider unready and block calls.
