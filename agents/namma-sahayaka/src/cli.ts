#!/usr/bin/env node

import * as readline from 'node:readline';
import { NammaSahayakaAgent, AgentResponse } from './agent/civic-agent.js';

function printBanner() {
  console.log(`
╔═════════════════════════════════════════════════════════════════════════════════╗
║                   ನಮ್ಮ ಸಹಾಯಕ — NAMMA SAHAYAKA                                    ║
║         Autonomous AI Civic Grievance & Ward Buddy for Bengaluru                ║
║         Built for GDG Cloud Bengaluru — Road to DevFest 2026                    ║
╚═════════════════════════════════════════════════════════════════════════════════╝
`);
}

function displayAgentResponse(res: AgentResponse) {
  console.log('\n' + '─'.repeat(80));
  console.log(`🔍 CITIZEN QUERY: "${res.query}"`);
  console.log(`🤖 AI REASONING ENGINE: ${res.modelUsed} (Latency: ${res.latencyMs}ms)`);
  console.log(`🛠️ TOOLS EXECUTED: ${res.toolCallsExecuted.join(' ➔ ')}`);
  console.log('─'.repeat(80));

  console.log(`\n📍 JURISDICTION & WARD DETAILS:`);
  console.log(`   • Locality:          ${res.ward.locality}`);
  console.log(`   • BBMP Ward:         No. ${res.ward.wardNumber} (${res.ward.wardName})`);
  console.log(`   • BBMP Zone:         ${res.ward.zone}`);
  console.log(`   • MLA Constituency:  ${res.ward.mlaConstituency}`);
  console.log(`   • BESCOM Unit:       ${res.ward.bescomSubdivision}`);
  console.log(`   • BWSSB Unit:        ${res.ward.bwssbServiceStation}`);

  console.log(`\n⚡ ACTION TRIAGE & CITIZEN SLA:`);
  console.log(`   • Responsible Body:  ${res.triage.agencyContact.fullName} (${res.triage.agency})`);
  console.log(`   • Kannada Name:      ${res.triage.agencyContact.fullNameKannada}`);
  console.log(`   • Issue Category:    ${res.triage.category.name}`);
  console.log(`   • Severity Level:    ${res.triage.severity.toUpperCase()} ${res.triage.isEmergency ? '⚠️ URGENT' : 'ℹ️ STANDARD'}`);
  console.log(`   • Guaranteed SLA:    ${res.triage.slaDaysFormatted}`);
  console.log(`   • Official Portal:   ${res.triage.agencyContact.portalUrl}`);
  console.log(`   • Primary Helpline:  ${res.triage.agencyContact.primaryHelpline}`);
  if (res.triage.agencyContact.whatsappBot) {
    console.log(`   • WhatsApp Helpdesk: ${res.triage.agencyContact.whatsappBot}`);
  }

  console.log(`\n🤖 AI GUIDANCE & CITIZEN SYNTHESIS:`);
  console.log(res.aiSynthesis.split('\n').map(l => `   ${l}`).join('\n'));

  console.log(`\n📜 FORMAL BILINGUAL ADMINISTRATIVE COMPLAINT:`);
  console.log(`   [Ref ID: ${res.bilingualComplaint.referenceId} | Date: ${res.bilingualComplaint.generatedDate}]`);
  console.log('\n   --- ENGLISH DRAFT ---');
  console.log(res.bilingualComplaint.english.body.split('\n').map(l => `   ${l}`).join('\n'));

  console.log('\n   --- ಅಧಿಕೃತ ಕನ್ನಡ ಪತ್ರ (KANNADA ADMINISTRATIVE DRAFT) ---');
  console.log(res.bilingualComplaint.kannada.body.split('\n').map(l => `   ${l}`).join('\n'));

  console.log(`\n🐦 PUBLIC ESCALATION DISPATCH:`);
  console.log(`   • X/Twitter Post (${res.dispatch.tweetLength} chars):`);
  console.log(`     "${res.dispatch.tweetText}"`);
  console.log(`   • WhatsApp Message Template:`);
  console.log(`     "${res.dispatch.whatsappMessageTemplate}"`);

  console.log(`\n📋 ESCALATION TIMELINE & ACTION CHECKLIST:`);
  res.dispatch.escalationChecklist.forEach(step => {
    console.log(`   ${step}`);
  });
  console.log('─'.repeat(80) + '\n');
}

async function runDemoMode(agent: NammaSahayakaAgent) {
  console.log('Running automated 3-scenario interactive demonstration...\n');

  const demoScenarios = [
    {
      title: 'Scenario 1: Mahadevapura Waterlogging (Event Venue Context)',
      query: 'Severe rainwater flooding on service road near Google Ananta, Bagmane Mahadevapura'
    },
    {
      title: 'Scenario 2: HSR Layout Pothole & Road Hazard',
      query: 'Large dangerous pothole on 27th Main HSR Layout road causing bike accidents'
    },
    {
      title: 'Scenario 3: Indiranagar Power Cut & Current Illa (Kanglish)',
      query: 'Current illa since 4 hours near 100ft road Indiranagar transformer trip'
    }
  ];

  for (const s of demoScenarios) {
    console.log(`\n▶ [DEMO] ${s.title}`);
    const res = await agent.processGrievance(s.query);
    displayAgentResponse(res);
  }

  console.log('Demonstration completed successfully.');
}

async function main() {
  printBanner();
  const agent = new NammaSahayakaAgent();
  const rawArgs = process.argv.slice(2);

  if (rawArgs.includes('--help') || rawArgs.includes('-h')) {
    console.log(`
Usage:
  # Interactive Chat Mode:
  npm start

  # One-shot Grievance Query:
  npm start -- "Pothole on 27th Main HSR Layout"
  npm start -- "Current illa since 4 hours in Indiranagar"
  npm start -- "Dirty Kaveri drinking water in Bellandur Ecospace"

  # Run Full Automated Benchmark / Eval Suite:
  npm run eval

  # Run 3-Scenario Demo Mode:
  npm run demo
`);
    process.exit(0);
  }

  if (rawArgs.includes('--demo')) {
    await runDemoMode(agent);
    process.exit(0);
  }

  // Non-flag query passed directly on CLI
  const queryArgs = rawArgs.filter(a => !a.startsWith('-'));
  if (queryArgs.length > 0) {
    const query = queryArgs.join(' ');
    const res = await agent.processGrievance(query);
    displayAgentResponse(res);
    process.exit(0);
  }

  // Interactive CLI Loop
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
  });

  const promptUser = () => {
    rl.question('Enter your civic problem / locality (or type "exit" to quit): ', async (input) => {
      const trimmed = input.trim();
      if (!trimmed || trimmed.toLowerCase() === 'exit' || trimmed.toLowerCase() === 'quit') {
        console.log('\nDhanyavadagalu! Thank you for using Namma Sahayaka.\n');
        rl.close();
        process.exit(0);
      }

      try {
        const res = await agent.processGrievance(trimmed);
        displayAgentResponse(res);
      } catch (err: any) {
        console.error('Error processing grievance:', err.message);
      }

      promptUser();
    });
  };

  promptUser();
}

main().catch(err => {
  console.error('Fatal CLI Error:', err);
  process.exit(1);
});
