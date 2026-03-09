const express = require("express");
const { classifyTicket } = require("./pipeline");

const app = express();
app.use(express.json());

app.post("/classify", async (req, res) => {
  const { ticket } = req.body;
  if (!ticket || typeof ticket !== "string") {
    return res.status(400).json({ error: "Missing 'ticket' field (string)" });
  }

  try {
    const classification = await classifyTicket(ticket);
    res.json(classification);
  } catch (err) {
    console.error("Classification error:", err.message);
    res.status(500).json({ error: "Classification failed" });
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Ticket classifier running on :${PORT}`));
