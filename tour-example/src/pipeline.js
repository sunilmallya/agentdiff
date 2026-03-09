const Anthropic = require("@anthropic-ai/sdk");
const { SYSTEM_PROMPT, buildPrompt } = require("./templates");
const { validateClassification } = require("./validator");
const examples = require("./examples.json");

const client = new Anthropic();

async function classifyTicket(ticketText, { retries = 2 } = {}) {
  const userPrompt = buildPrompt(ticketText, examples);

  for (let attempt = 0; attempt <= retries; attempt++) {
    const response = await client.messages.create({
      model: "claude-haiku-4-5-20251001",
      max_tokens: 512,
      system: SYSTEM_PROMPT,
      messages: [{ role: "user", content: userPrompt }],
    });

    const text = response.content[0].text;
    const result = validateClassification(text);

    if (result.success) {
      return result.data;
    }

    if (attempt < retries) {
      console.warn(`Validation failed (attempt ${attempt + 1}), retrying...`);
    }
  }

  throw new Error("Classification failed after retries — output did not match schema");
}

module.exports = { classifyTicket };
