import { NextResponse } from "next/server";
import { generateContent } from "@/lib/gemini";

type Ctx = Record<string, unknown>;
function sub(ctx: Ctx, key: string): Record<string, unknown> {
  return (ctx[key] as Record<string, unknown>) || {};
}

const STEP_PROMPTS: Record<number, (ctx: Record<string, unknown>) => string> = {
  1: (ctx) => `You are a quality management expert. A manufacturing quality problem has been reported:
Title: ${ctx.title}
Plant: ${ctx.plant}
Product: ${ctx.product}

Generate D1 (Team Formation) suggestions in this exact JSON format:
{
  "teamLeader": "Name with role/title",
  "members": [
    { "name": "Name", "role": "Role", "department": "Dept" },
    { "name": "Name", "role": "Role", "department": "Dept" },
    { "name": "Name", "role": "Role", "department": "Dept" },
    { "name": "Name", "role": "Role", "department": "Dept" }
  ],
  "meetingDate": "YYYY-MM-DD (suggest within 2 days)",
  "rationale": "Why these team members were chosen"
}
Return only valid JSON, no markdown.`,

  2: (ctx) => `Quality problem: ${ctx.title}
Plant: ${ctx.plant}, Product: ${ctx.product}
Initial description: ${ctx.description || "Not provided"}

Generate D2 (Problem Description) in this exact JSON format:
{
  "problemStatement": "Clear, specific problem statement",
  "what": "What exactly is wrong",
  "when": "When was it first detected",
  "where": "Where in the process/product",
  "who": "Who is affected",
  "howMany": "Estimated quantity/scope affected",
  "isNot": "What the problem is NOT (boundary)",
  "severity": "High/Medium/Low",
  "customerImpact": "Impact on customer/production"
}
Return only valid JSON, no markdown.`,

  3: (ctx) => `Problem: ${ctx.title}
Problem statement: ${sub(ctx,"d2").problemStatement || ctx.title}
Severity: ${sub(ctx,"d2").severity || "Medium"}

Generate D3 (Containment Actions) in this exact JSON format:
{
  "immediateActions": [
    { "action": "Action description", "owner": "Role", "dueDate": "YYYY-MM-DD", "status": "Open" },
    { "action": "Action description", "owner": "Role", "dueDate": "YYYY-MM-DD", "status": "Open" },
    { "action": "Action description", "owner": "Role", "dueDate": "YYYY-MM-DD", "status": "Open" }
  ],
  "stockHold": "Describe if any product hold/quarantine is needed",
  "customerNotification": "Whether and how to notify customer",
  "effectivenessCheck": "How to verify containment is working"
}
Return only valid JSON, no markdown.`,

  4: (ctx) => `Problem: ${ctx.title}
Root issue: ${sub(ctx,"d2").what || ctx.title}
Containment: ${JSON.stringify(ctx.d3 || {})}

Generate D4 (Root Cause Analysis) in this exact JSON format:
{
  "fishbone": {
    "effect": "${ctx.title}",
    "categories": {
      "Man": ["cause1", "cause2"],
      "Machine": ["cause1", "cause2"],
      "Material": ["cause1", "cause2"],
      "Method": ["cause1", "cause2"],
      "Measurement": ["cause1", "cause2"],
      "Environment": ["cause1", "cause2"]
    }
  },
  "fiveWhy": [
    { "why": "Why #1 question", "answer": "Answer 1" },
    { "why": "Why #2 question", "answer": "Answer 2" },
    { "why": "Why #3 question", "answer": "Answer 3" },
    { "why": "Why #4 question", "answer": "Answer 4" },
    { "why": "Why #5 question", "answer": "Answer 5" }
  ],
  "rootCause": "The identified root cause statement",
  "escapeCause": "Why the problem was not caught earlier"
}
Return only valid JSON, no markdown.`,

  5: (ctx) => `Root cause identified: ${sub(ctx,"d4").rootCause || ""}
Problem: ${ctx.title}

Generate D5 (Root Cause Verification) in this exact JSON format:
{
  "verificationMethods": [
    { "method": "Method description", "result": "Expected result", "responsible": "Role" },
    { "method": "Method description", "result": "Expected result", "responsible": "Role" }
  ],
  "evidenceRequired": ["Evidence item 1", "Evidence item 2", "Evidence item 3"],
  "verificationStatus": "Pending",
  "conclusion": "Summary of verification approach"
}
Return only valid JSON, no markdown.`,

  6: (ctx) => `Root cause: ${sub(ctx,"d4").rootCause || ""}
Problem: ${ctx.title}

Generate D6 (Corrective Actions) in this exact JSON format:
{
  "actions": [
    { "action": "Specific corrective action", "owner": "Role/Dept", "targetDate": "YYYY-MM-DD", "priority": "High", "status": "Open" },
    { "action": "Specific corrective action", "owner": "Role/Dept", "targetDate": "YYYY-MM-DD", "priority": "Medium", "status": "Open" },
    { "action": "Specific corrective action", "owner": "Role/Dept", "targetDate": "YYYY-MM-DD", "priority": "Medium", "status": "Open" }
  ],
  "implementationPlan": "Overall plan description",
  "successCriteria": "How we know the corrective actions worked",
  "reviewDate": "YYYY-MM-DD"
}
Return only valid JSON, no markdown.`,

  7: (ctx) => `Problem: ${ctx.title}
Root cause: ${sub(ctx,"d4").rootCause || ""}
Corrective actions: ${JSON.stringify((sub(ctx,"d6").actions as unknown[]) || [])}

Generate D7 (Preventive Actions) in this exact JSON format:
{
  "systemChanges": [
    { "change": "System/process change", "area": "Affected area", "owner": "Role", "dueDate": "YYYY-MM-DD" },
    { "change": "System/process change", "area": "Affected area", "owner": "Role", "dueDate": "YYYY-MM-DD" }
  ],
  "similarProcesses": ["Process/product 1 to check", "Process/product 2 to check"],
  "trainingRequired": "Training needs identified",
  "documentUpdates": ["Document 1 to update", "Document 2 to update"],
  "controlPlan": "How to prevent recurrence long-term"
}
Return only valid JSON, no markdown.`,

  8: (ctx) => `8D Problem: ${ctx.title}
Root Cause: ${sub(ctx,"d4").rootCause || ""}
Corrective Actions: ${JSON.stringify((sub(ctx,"d6").actions as unknown[]) || [])}
Preventive Actions: ${JSON.stringify((sub(ctx,"d7").systemChanges as unknown[]) || [])}

Generate D8 (Team Recognition & Closure) in this exact JSON format:
{
  "summary": "Executive summary of the 8D journey and resolution",
  "keyLearnings": ["Learning 1", "Learning 2", "Learning 3"],
  "teamAcknowledgment": "Recognition message for the team",
  "lessonsLearned": "Broader lessons for the organization",
  "closureDate": "YYYY-MM-DD",
  "effectiveness": "How effectiveness will be measured going forward"
}
Return only valid JSON, no markdown.`,
};

export async function POST(req: Request) {
  const body = await req.json();
  const { stepNumber, context } = body;

  if (!STEP_PROMPTS[stepNumber]) {
    return NextResponse.json({ error: "Invalid step" }, { status: 400 });
  }

  try {
    const prompt = STEP_PROMPTS[stepNumber](context);
    const raw = await generateContent(prompt);
    const cleaned = raw.replace(/```json\n?/g, "").replace(/```\n?/g, "").trim();
    const suggestion = JSON.parse(cleaned);
    return NextResponse.json({ suggestion });
  } catch (err) {
    console.error("Gemini error:", err);
    return NextResponse.json({ error: "AI generation failed" }, { status: 500 });
  }
}
