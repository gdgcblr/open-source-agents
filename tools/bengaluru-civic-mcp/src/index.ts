#!/usr/bin/env node

/**
 * Bengaluru Civic Intelligence MCP Server & Developer Utility
 * Model Context Protocol (MCP) tool suite for municipal jurisdiction lookup,
 * civic grievance triage, and bilingual Kannada complaint generation.
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  Tool
} from '@modelcontextprotocol/sdk/types.js';

import { WardResolver } from './services/ward-resolver.js';
import { TriageEngine } from './services/triage-engine.js';
import { BilingualFormatter } from './services/bilingual-formatter.js';
import { SocialDispatcher } from './services/social-dispatcher.js';
import { BANGALORE_WARDS, AGENCY_CONTACTS, CIVIC_CATEGORIES } from './data/civic-data.js';

// Define MCP Tools
const TOOLS: Tool[] = [
  {
    name: 'lookup_ward_jurisdiction',
    description: 'Look up Bengaluru BBMP Ward number, Ward name, Zone, MLA Constituency, BESCOM electricity subdivision, and BWSSB water service station from any locality, landmark, or PIN code.',
    inputSchema: {
      type: 'object',
      properties: {
        query: {
          type: 'string',
          description: 'Bengaluru locality name, landmark, or 6-digit PIN code (e.g., "Mahadevapura", "560102", "Google Ananta", "HSR Layout", "Sony World Signal", "Whitefield")'
        }
      },
      required: ['query']
    }
  },
  {
    name: 'classify_and_triage_issue',
    description: 'Analyze and triage a civic problem (potholes, garbage, power cuts, water leaks, sewage, traffic signals), identifying the responsible agency (BBMP, BESCOM, BWSSB, BTP) and expected SLA resolution timeline.',
    inputSchema: {
      type: 'object',
      properties: {
        description: {
          type: 'string',
          description: 'Description of the civic complaint in English, Kannada, or mixed Kanglish (e.g., "huge pothole on road", "current illa transformer blast", "dirty water coming in tap")'
        },
        overrideSeverity: {
          type: 'string',
          enum: ['critical', 'moderate', 'standard'],
          description: 'Optional manual severity override'
        }
      },
      required: ['description']
    }
  },
  {
    name: 'generate_bilingual_complaint',
    description: 'Generate a formal, administrative complaint letter in BOTH English and authentic official Kannada with location details, ward reference, and proper administrative vocabulary.',
    inputSchema: {
      type: 'object',
      properties: {
        locality: {
          type: 'string',
          description: 'Locality or area name (e.g., "HSR Layout", "Bellandur", "Indiranagar")'
        },
        description: {
          type: 'string',
          description: 'Detailed description of the issue'
        },
        landmark: {
          type: 'string',
          description: 'Optional specific street or landmark (e.g., "Near 27th Main Signal")'
        },
        citizenName: {
          type: 'string',
          description: 'Optional citizen name for formal signoff'
        },
        contactNumber: {
          type: 'string',
          description: 'Optional phone number for department follow-up'
        }
      },
      required: ['locality', 'description']
    }
  },
  {
    name: 'generate_escalation_dispatch',
    description: 'Generate social media escalation content (X/Twitter post under 280 chars with official handles @BBMPCOMM, @NammaBESCOM, @BWSSBOnline), WhatsApp message template, 24x7 helpline numbers, and multi-tier escalation checklist.',
    inputSchema: {
      type: 'object',
      properties: {
        locality: {
          type: 'string',
          description: 'Locality or area name'
        },
        description: {
          type: 'string',
          description: 'Description of the grievance'
        },
        landmark: {
          type: 'string',
          description: 'Optional specific street or landmark'
        }
      },
      required: ['locality', 'description']
    }
  },
  {
    name: 'get_bengaluru_civic_directory',
    description: 'Retrieve a directory of all indexed Bengaluru BBMP wards, zones, and official municipal emergency helplines.',
    inputSchema: {
      type: 'object',
      properties: {
        zone: {
          type: 'string',
          description: 'Optional BBMP Zone filter (e.g., "Mahadevapura", "Bommanahalli", "South", "East", "West", "Yelahanka")'
        }
      }
    }
  }
];

// Tool execution logic
export async function executeTool(name: string, args: Record<string, any>) {
  switch (name) {
    case 'lookup_ward_jurisdiction': {
      const query = String(args.query || '');
      const result = WardResolver.resolve(query);
      return {
        content: [{ type: 'text', text: JSON.stringify(result, null, 2) }]
      };
    }

    case 'classify_and_triage_issue': {
      const desc = String(args.description || '');
      const severity = args.overrideSeverity as 'critical' | 'moderate' | 'standard' | undefined;
      const result = TriageEngine.classify(desc, severity);
      return {
        content: [{ type: 'text', text: JSON.stringify(result, null, 2) }]
      };
    }

    case 'generate_bilingual_complaint': {
      const loc = String(args.locality || '');
      const desc = String(args.description || '');
      const landmark = args.landmark ? String(args.landmark) : undefined;
      const citizenName = args.citizenName ? String(args.citizenName) : undefined;
      const contactNumber = args.contactNumber ? String(args.contactNumber) : undefined;

      const wardRes = WardResolver.resolve(loc);
      const ward = wardRes.matchedWard!;
      const triage = TriageEngine.classify(desc);

      const complaint = BilingualFormatter.generate({
        ward,
        agencyContact: triage.agencyContact,
        category: triage.category,
        description: desc,
        landmark,
        citizenName,
        contactNumber
      });

      return {
        content: [{ type: 'text', text: JSON.stringify(complaint, null, 2) }]
      };
    }

    case 'generate_escalation_dispatch': {
      const loc = String(args.locality || '');
      const desc = String(args.description || '');
      const landmark = args.landmark ? String(args.landmark) : undefined;

      const wardRes = WardResolver.resolve(loc);
      const ward = wardRes.matchedWard!;
      const triage = TriageEngine.classify(desc);

      const dispatch = SocialDispatcher.generateDispatch({
        ward,
        agencyContact: triage.agencyContact,
        category: triage.category,
        description: desc,
        landmark
      });

      return {
        content: [{ type: 'text', text: JSON.stringify(dispatch, null, 2) }]
      };
    }

    case 'get_bengaluru_civic_directory': {
      const zoneFilter = args.zone ? String(args.zone).toLowerCase() : undefined;
      const wards = zoneFilter
        ? BANGALORE_WARDS.filter(w => w.zone.toLowerCase().includes(zoneFilter))
        : BANGALORE_WARDS;

      return {
        content: [{
          type: 'text',
          text: JSON.stringify({
            totalIndexedWards: wards.length,
            agencies: AGENCY_CONTACTS,
            wards: wards.map(w => ({
              locality: w.locality,
              wardNumber: w.wardNumber,
              wardName: w.wardName,
              zone: w.zone,
              pincodes: w.pinCodes,
              mlaConstituency: w.mlaConstituency,
              bescomSubdivision: w.bescomSubdivision,
              bwssbServiceStation: w.bwssbServiceStation
            }))
          }, null, 2)
        }]
      };
    }

    default:
      throw new Error(`Unknown tool: ${name}`);
  }
}

// Standalone CLI mode handler
async function runCliMode() {
  const args = process.argv.slice(2);

  if (args.includes('--help') || args.includes('-h') || args.length === 0) {
    console.log(`
╔═══════════════════════════════════════════════════════════════════╗
║         bengaluru-civic-mcp — Civic Intelligence Suite            ║
║     GDG Cloud Bengaluru Community Open-Source AI Contribution     ║
╚═══════════════════════════════════════════════════════════════════╝

Usage:
  # Run as standard MCP Server (stdio protocol for Claude/Cursor/Antigravity):
  node dist/index.js

  # Interactive CLI / Quick Test Mode:
  node dist/index.js --lookup <locality/pincode>
  node dist/index.js --triage "<issue description>"
  node dist/index.js --complaint --locality "<locality>" --desc "<issue>"
  node dist/index.js --dispatch --locality "<locality>" --desc "<issue>"
  node dist/index.js --directory [--zone <zone_name>]

Examples:
  node dist/index.js --lookup "Mahadevapura"
  node dist/index.js --triage "Deep pothole near 27th Main HSR causing bike falls"
  node dist/index.js --complaint --locality "Bellandur" --desc "Contaminated muddy water from Kaveri pipeline"
`);
    process.exit(0);
  }

  try {
    if (args.includes('--lookup')) {
      const idx = args.indexOf('--lookup');
      const query = args[idx + 1] || 'Mahadevapura';
      const res = await executeTool('lookup_ward_jurisdiction', { query });
      console.log(res.content[0].text);
      process.exit(0);
    }

    if (args.includes('--triage')) {
      const idx = args.indexOf('--triage');
      const desc = args[idx + 1] || 'Broken streetlights and dark stretch';
      const res = await executeTool('classify_and_triage_issue', { description: desc });
      console.log(res.content[0].text);
      process.exit(0);
    }

    if (args.includes('--complaint')) {
      const locIdx = args.indexOf('--locality');
      const descIdx = args.indexOf('--desc');
      const loc = locIdx !== -1 ? args[locIdx + 1] : 'HSR Layout';
      const desc = descIdx !== -1 ? args[descIdx + 1] : 'Severe pothole crater on main road';
      const res = await executeTool('generate_bilingual_complaint', { locality: loc, description: desc });
      console.log(res.content[0].text);
      process.exit(0);
    }

    if (args.includes('--dispatch')) {
      const locIdx = args.indexOf('--locality');
      const descIdx = args.indexOf('--desc');
      const loc = locIdx !== -1 ? args[locIdx + 1] : 'Mahadevapura';
      const desc = descIdx !== -1 ? args[descIdx + 1] : 'Waterlogging on service road near Google Ananta';
      const res = await executeTool('generate_escalation_dispatch', { locality: loc, description: desc });
      console.log(res.content[0].text);
      process.exit(0);
    }

    if (args.includes('--directory')) {
      const zoneIdx = args.indexOf('--zone');
      const zone = zoneIdx !== -1 ? args[zoneIdx + 1] : undefined;
      const res = await executeTool('get_bengaluru_civic_directory', { zone });
      console.log(res.content[0].text);
      process.exit(0);
    }
  } catch (err: any) {
    console.error('Error running CLI command:', err.message);
    process.exit(1);
  }
}

// Start Server or CLI
async function main() {
  const isCli = process.argv.slice(2).some(arg => arg.startsWith('--') || arg.startsWith('-'));

  if (isCli) {
    await runCliMode();
    return;
  }

  // MCP Server Mode over stdio
  const server = new Server(
    {
      name: 'bengaluru-civic-mcp',
      version: '1.0.0'
    },
    {
      capabilities: {
        tools: {}
      }
    }
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: TOOLS
  }));

  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    try {
      const result = await executeTool(request.params.name, request.params.arguments || {});
      return result;
    } catch (error: any) {
      return {
        isError: true,
        content: [{ type: 'text', text: `Error executing tool ${request.params.name}: ${error.message}` }]
      };
    }
  });

  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error('Bengaluru Civic MCP Server running on stdio');
}

import { fileURLToPath } from 'node:url';

// Check if this script is executed directly
const isDirectExecution = Boolean(
  process.argv[1] &&
  !process.env.NODE_TEST_CONTEXT &&
  (
    fileURLToPath(import.meta.url) === process.argv[1] ||
    process.argv[1].endsWith('dist/index.js') ||
    process.argv[1].endsWith('dist/src/index.js')
  )
);

if (isDirectExecution) {
  main().catch((err) => {
    console.error('Fatal error in Bengaluru Civic MCP Server:', err);
    process.exit(1);
  });
}

