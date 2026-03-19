# Demo adapters

These files are example provider-specific adapters for the Crossplane demo.

## Files

- `akamai_adapter.py`
- `cloudflare_adapter.py`
- `demo_runner.py`

## What they do

They take the same canonical `XDeliveryService` intent and render it into two different provider-specific shapes.

That is the point you want your director to see:

- one bank-owned intent
- different provider-native outputs
- no app team needs to learn Akamai rule trees or Cloudflare ruleset phases

## Run it

```bash
cd adapters
python3 demo_runner.py
```

## Important

These are demo translators only.
They do not call real vendor APIs.
They exist to explain the semantic normalization problem and the adapter pattern.
