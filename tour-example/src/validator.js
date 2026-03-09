const { z } = require("zod");

const TicketClassification = z.object({
  intent: z.enum([
    "refund_request",
    "order_status",
    "cancellation",
    "product_issue",
    "account_access",
    "billing_dispute",
    "shipping_delay",
    "other",
  ]),
  urgency: z.enum(["low", "medium", "high", "critical"]),
  sentiment: z.enum(["frustrated", "neutral", "satisfied"]),
  language: z.string().min(2).max(5),
  summary: z.string().min(10).max(300),
  suggested_action: z.string().min(5).max(500),
  requires_escalation: z.boolean(),
});

function validateClassification(raw) {
  try {
    const text = typeof raw === "string" ? raw.trim() : JSON.stringify(raw);
    const parsed = JSON.parse(text);
    return { success: true, data: TicketClassification.parse(parsed) };
  } catch (err) {
    return { success: false, error: err.message };
  }
}

module.exports = { TicketClassification, validateClassification };
