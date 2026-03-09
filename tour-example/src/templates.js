const SYSTEM_PROMPT = `You are a support ticket classifier for an e-commerce platform.
Analyze each ticket and extract structured data.

Always respond in valid JSON. No markdown, no explanation — just the JSON object.`;

const CLASSIFY_PROMPT = `Classify this support ticket.

<ticket>
{ticket_text}
</ticket>

Extract:
1. intent — one of: refund_request, order_status, cancellation, product_issue, account_access, billing_dispute, shipping_delay, other
2. urgency — one of: low, medium, high, critical
3. sentiment — one of: frustrated, neutral, satisfied
4. language — the ISO 639-1 code of the ticket language
5. summary — a one-sentence summary in English regardless of input language
6. suggested_action — what the support agent should do first
7. requires_escalation — true if this needs a supervisor (e.g. legal threats, safety issues, repeated failures)

For intent classification:
- "refund_request" = customer explicitly asks for money back
- "cancellation" = customer wants to cancel a future order or subscription, NOT get money back for a past one
- "billing_dispute" = customer says they were charged incorrectly or don't recognize a charge
- "product_issue" = item arrived damaged, wrong item, or doesn't work as described

<examples>
{few_shot_examples}
</examples>

Respond with a JSON object matching this exact schema:
{{
  "intent": string,
  "urgency": string,
  "sentiment": string,
  "language": string,
  "summary": string,
  "suggested_action": string,
  "requires_escalation": boolean
}}`;

function buildPrompt(ticketText, examples) {
  const exampleBlock = examples
    .map(
      (ex, i) =>
        `<example>\nTicket: ${ex.input}\nOutput: ${JSON.stringify(ex.output)}\n</example>`
    )
    .join("\n\n");

  return CLASSIFY_PROMPT
    .replace("{ticket_text}", ticketText)
    .replace("{few_shot_examples}", exampleBlock);
}

module.exports = { SYSTEM_PROMPT, CLASSIFY_PROMPT, buildPrompt };
