import { GoogleGenAI, Type, FunctionDeclaration } from '@google/genai';
import * as dotenv from 'dotenv';
import { WardResolver, WardLookupResult } from '../tools/services/ward-resolver.js';
import { TriageEngine, TriageResult } from '../tools/services/triage-engine.js';
import { BilingualFormatter, BilingualComplaintResult } from '../tools/services/bilingual-formatter.js';
import { SocialDispatcher, DispatchPackage } from '../tools/services/social-dispatcher.js';
import { WardInfo } from '../tools/data/civic-data.js';

dotenv.config();

// Official Google GenAI Tool Declarations
export const GOOGLE_GENAI_CIVIC_TOOLS: FunctionDeclaration[] = [
  {
    name: 'lookup_ward_jurisdiction',
    description: 'Look up Bengaluru BBMP Ward number, Ward name, Zone, MLA Constituency, BESCOM electricity subdivision, and BWSSB water station from any locality, landmark, or PIN code.',
    parameters: {
      type: Type.OBJECT,
      properties: {
        query: {
          type: Type.STRING,
          description: 'Bengaluru locality name, landmark, or 6-digit PIN code (e.g., Mahadevapura, HSR Layout, 560102, Google Ananta)'
        }
      },
      required: ['query']
    }
  },
  {
    name: 'classify_and_triage_issue',
    description: 'Analyze and triage a civic problem (potholes, garbage, power cuts, water leaks, sewage, traffic signals), identifying the responsible agency (BBMP, BESCOM, BWSSB, BTP) and expected SLA resolution timeline.',
    parameters: {
      type: Type.OBJECT,
      properties: {
        description: {
          type: Type.STRING,
          description: 'Description of the civic complaint in English, Kannada, or Kanglish'
        }
      },
      required: ['description']
    }
  },
  {
    name: 'generate_bilingual_complaint',
    description: 'Generate a formal, administrative complaint letter in BOTH English and authentic official Kannada with location details, ward reference, and proper administrative vocabulary.',
    parameters: {
      type: Type.OBJECT,
      properties: {
        locality: { type: Type.STRING, description: 'Locality or area name' },
        description: { type: Type.STRING, description: 'Detailed description of the issue' }
      },
      required: ['locality', 'description']
    }
  },
  {
    name: 'generate_escalation_dispatch',
    description: 'Generate social media escalation content (X/Twitter post under 280 chars with official handles @BBMPCOMM, @NammaBESCOM, @BWSSBOnline), WhatsApp message template, 24x7 helpline numbers, and multi-tier escalation checklist.',
    parameters: {
      type: Type.OBJECT,
      properties: {
        locality: { type: Type.STRING, description: 'Locality or area name' },
        description: { type: Type.STRING, description: 'Description of the grievance' }
      },
      required: ['locality', 'description']
    }
  }
];


export interface AgentResponse {
  query: string;
  ward: WardInfo;
  triage: TriageResult;
  bilingualComplaint: BilingualComplaintResult;
  dispatch: DispatchPackage;
  aiSynthesis: string;
  modelUsed: string;
  toolCallsExecuted: string[];
  latencyMs: number;
}

export class NammaSahayakaAgent {
  private genAI: GoogleGenAI | null = null;
  private modelName: string;

  constructor(apiKey?: string, modelName = 'gemini-3.8-flash') {
    const key = apiKey || process.env.GEMINI_API_KEY;
    this.modelName = process.env.MODEL_NAME || modelName;
    if (key && key !== 'your_gemini_api_key_here') {
      try {
        this.genAI = new GoogleGenAI({ apiKey: key });
      } catch (err) {
        console.warn('Could not initialize GoogleGenAI client, defaulting to simulation mode.');
      }
    }
  }

  /**
   * Main agent entry point: processes citizen grievance through multi-step reasoning,
   * tool execution, and bilingual response generation.
   */
  async processGrievance(userInput: string, options?: {
    citizenName?: string;
    contactNumber?: string;
    forceMock?: boolean;
  }): Promise<AgentResponse> {
    const startTime = Date.now();
    const toolCallsExecuted: string[] = [];

    // Step 1: Tool Execution (Ward Resolution)
    toolCallsExecuted.push('lookup_ward_jurisdiction');
    const wardResult: WardLookupResult = WardResolver.resolve(userInput);
    const ward = wardResult.matchedWard!;

    // Step 2: Tool Execution (Triage & Agency Routing)
    toolCallsExecuted.push('classify_and_triage_issue');
    const triage: TriageResult = TriageEngine.classify(userInput);

    // Step 3: Tool Execution (Bilingual Complaint Generation)
    toolCallsExecuted.push('generate_bilingual_complaint');
    const complaint: BilingualComplaintResult = BilingualFormatter.generate({
      ward,
      agencyContact: triage.agencyContact,
      category: triage.category,
      description: userInput,
      landmark: wardResult.confidence === 'alias' ? userInput : undefined,
      citizenName: options?.citizenName,
      contactNumber: options?.contactNumber
    });

    // Step 4: Tool Execution (Social Escalation & Helpline Dispatch)
    toolCallsExecuted.push('generate_escalation_dispatch');
    const dispatch: DispatchPackage = SocialDispatcher.generateDispatch({
      ward,
      agencyContact: triage.agencyContact,
      category: triage.category,
      description: userInput
    });

    // Step 5: AI Synthesis (Gemini or Deterministic Reasoning)
    let aiSynthesis = '';
    let modelUsed = 'namma-deterministic-v1';

    if (this.genAI && !options?.forceMock) {
      try {
        const prompt = `You are "Namma Sahayaka", an empathetic, civic-minded AI assistant for citizens in Bengaluru.
A citizen has reported the following problem:
"${userInput}"

Our tools have analyzed and determined:
- Location / Ward: ${ward.locality} (Ward No. ${ward.wardNumber}: ${ward.wardName}, Zone: ${ward.zone})
- Responsible Agency: ${triage.agencyContact.fullName} (${triage.agency})
- Category: ${triage.category.name}
- Severity: ${triage.severity.toUpperCase()} (SLA: ${triage.slaDaysFormatted})
- Official Helpline: ${triage.agencyContact.primaryHelpline} (WhatsApp: ${triage.agencyContact.whatsappBot || 'N/A'})
- Twitter Tag: ${triage.agencyContact.twitterHandle}

Please provide a concise, empowering, 2-paragraph guidance response:
1. First paragraph in English: Empathize with the citizen, state the exact responsible division, explain immediate action steps, and state the SLA resolution timeline.
2. Second paragraph in friendly, conversational Kannada (with English transliteration/clarity if needed): Offer encouragement and state the helpline number.
Keep tone respectful, practical, and action-oriented.`;

        const response = await this.genAI.models.generateContent({
          model: this.modelName,
          contents: prompt,
          config: {
            tools: [{ functionDeclarations: GOOGLE_GENAI_CIVIC_TOOLS }]
          }
        });

        if (response && response.text) {
          aiSynthesis = response.text.trim();
          modelUsed = this.modelName;
        }
      } catch (err: any) {
        console.warn(`[Gemini API Note] Using deterministic reasoning: ${err.message}`);
      }
    }

    if (!aiSynthesis) {
      aiSynthesis = `Hello! I have analyzed your report and routed it directly to ${triage.agencyContact.fullName} (${triage.agency}). Your grievance is classified under "${triage.category.name}" in ${ward.locality} (Ward ${ward.wardNumber}: ${ward.wardName}, ${ward.zone} Zone). Under the Bengaluru Citizen Charter, the guaranteed SLA for this issue is ${triage.slaDaysFormatted}. Please call the 24x7 helpline at ${triage.agencyContact.primaryHelpline} or message WhatsApp ${triage.agencyContact.whatsappBot || triage.agencyContact.primaryHelpline} with your reference code ${complaint.referenceId}.

ನಮಸ್ಕಾರ, ನಿಮ್ಮ ದೂರನ್ನು ${triage.agencyContact.fullNameKannada} ಗೆ ನಿಗದಿಪಡಿಸಲಾಗಿದೆ. ನಿಮ್ಮ ವಾರ್ಡ್ ಸಂಖ್ಯೆ ${ward.wardNumber} (${ward.wardName}). ತುರ್ತು ಸಹಾಯಕ್ಕಾಗಿ 24x7 ಸಹಾಯವಾಣಿ ${triage.agencyContact.primaryHelpline} ಗೆ ಕರೆ ಮಾಡಿ ಅಥವಾ ಅಧಿಕೃತ ಪೋರ್ಟಲ್‌ನಲ್ಲಿ ದೂರು ದಾಖಲಿಸಿ. ನಾವು ನಿಮ್ಮೊಂದಿಗೆ ಇದ್ದೇವೆ!`;
    }

    const latencyMs = Date.now() - startTime;

    return {
      query: userInput,
      ward,
      triage,
      bilingualComplaint: complaint,
      dispatch,
      aiSynthesis,
      modelUsed,
      toolCallsExecuted,
      latencyMs
    };
  }
}
