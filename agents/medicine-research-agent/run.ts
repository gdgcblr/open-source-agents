import { 
  InMemoryRunner, 
  isFinalResponse, 
  stringifyContent,
  getFunctionCalls,
  getFunctionResponses
} from '@google/adk';
import { prescriptionResearchWorkflow } from './medicalpipelines.js';
import * as fs from 'fs';

async function main() {
  const imagePath = './sampleTestData/sample_prescription.jpg';
  const imageBase64 = fs.readFileSync(imagePath).toString('base64');

  const runner = new InMemoryRunner({
    agent: prescriptionResearchWorkflow,
    appName: 'medicine_safety_app',
  });

  const userId = 'patient_user';
  const sessionId = 'session_001';

  await runner.sessionService.createSession({
    appName: runner.appName,
    userId,
    sessionId,
  });

  console.log('🚀 Running Multi-Agent Medicine Workflow...\n');

  const eventStream = runner.runAsync({
    userId,
    sessionId,
    newMessage: {
      role: 'user',
      parts: [
        {
          text: `Evaluate this prescription:
- Patient: Female, 29 years old
- Status: 2nd Trimester Pregnancy
- Existing conditions: Chronic Hypertension
- Allergies: Penicillin`,
        },
        {
          inlineData: {
            mimeType: 'image/jpeg',
            data: imageBase64,
          },
        },
      ],
    },
  });

  let finalPlan = '';

  for await (const event of eventStream) {
    // 1. Identify which agent authored the event
    if (event.author) {
      console.log(`\n[Agent: ${event.author}]`);
    }

    // 2. Safely inspect tool calls (Function Calls) using the ADK helper
    const functionCalls = getFunctionCalls(event);
    if (functionCalls && functionCalls.length > 0) {
      for (const call of functionCalls) {
        console.log(`  🔧 Invoked Tool: "${call.name}" with args:`, JSON.stringify(call.args));
      }
    }

    // 3. (Optional) Inspect the responses returned by the tools
    const functionResponses = getFunctionResponses(event);
    if (functionResponses && functionResponses.length > 0) {
      for (const resp of functionResponses) {
        console.log(`  📦 Tool "${resp.name}" completed.`);
      }
    }

    // 4. Capture the final synthesized Care Plan
    if (isFinalResponse(event)) {
      finalPlan = stringifyContent(event);
    }
  }

  console.log('\n==================================================');
  console.log('📋 FINAL SAFETY AUDIT & MEDICATION PLAN');
  console.log('==================================================\n');
  console.log(finalPlan);
}

main().catch(console.error);