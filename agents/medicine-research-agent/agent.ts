import { prescriptionResearchWorkflow } from './medicalpipelines.js';

// Export your workflow/agent as the default or root agent for adk-devtools
export default prescriptionResearchWorkflow;
export const rootAgent = prescriptionResearchWorkflow;