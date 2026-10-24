import {
  CIVIC_CATEGORIES,
  AGENCY_CONTACTS,
  CivicCategory,
  AgencyContact,
  CivicAgency
} from '../data/civic-data.js';

export interface TriageResult {
  category: CivicCategory;
  agency: CivicAgency;
  agencyContact: AgencyContact;
  severity: 'critical' | 'moderate' | 'standard';
  slaHours: number;
  slaDaysFormatted: string;
  isEmergency: boolean;
  actionSummary: string;
  actionSummaryKannada: string;
}

export class TriageEngine {
  /**
   * Evaluates citizen grievance text and routes to responsible municipal body
   * with severity and SLA estimation.
   */
  static classify(description: string, overrideSeverity?: 'critical' | 'moderate' | 'standard'): TriageResult {
    const text = description.toLowerCase();

    let matchedCategory: CivicCategory | undefined;
    let maxKeywordScore = 0;

    for (const cat of CIVIC_CATEGORIES) {
      let score = 0;
      for (const kw of cat.keywords) {
        if (text.includes(kw)) {
          score += kw.includes(' ') ? 3 : 2;
        }
      }
      for (const kkw of cat.kannadaKeywords) {
        if (text.includes(kkw)) {
          score += 4;
        }
      }

      if (score > maxKeywordScore) {
        maxKeywordScore = score;
        matchedCategory = cat;
      }
    }

    // Default to BBMP road damage if generic
    if (!matchedCategory) {
      if (text.includes('water') || text.includes('drain')) {
        matchedCategory = CIVIC_CATEGORIES.find(c => c.id === 'water_leakage_contamination')!;
      } else if (text.includes('electric') || text.includes('power') || text.includes('wire')) {
        matchedCategory = CIVIC_CATEGORIES.find(c => c.id === 'power_outage')!;
      } else {
        matchedCategory = CIVIC_CATEGORIES.find(c => c.id === 'pothole_road')!;
      }
    }

    // Determine severity
    const criticalUrgencyWords = [
      'urgent', 'emergency', 'danger', 'accident', 'sparking', 'burst', 'flooding',
      'hospital', 'school', 'fallen pole', 'threat', 'open manhole', 'death trap',
      'ತುರ್ತು', 'ಅಪಾಯ', 'ಸಾವು'
    ];
    const isExplicitlyCritical = criticalUrgencyWords.some(w => text.includes(w));

    let finalSeverity: 'critical' | 'moderate' | 'standard' =
      overrideSeverity || (isExplicitlyCritical ? 'critical' : matchedCategory.defaultSeverity);

    const agencyContact = AGENCY_CONTACTS[matchedCategory.agency];
    const slaHours = agencyContact.slaHours[finalSeverity];

    const days = Math.round(slaHours / 24);
    const slaDaysFormatted = slaHours < 24 ? `${slaHours} Hours` : `${days} Day${days > 1 ? 's' : ''} (${slaHours} Hours)`;

    return {
      category: matchedCategory,
      agency: matchedCategory.agency,
      agencyContact,
      severity: finalSeverity,
      slaHours,
      slaDaysFormatted,
      isEmergency: finalSeverity === 'critical',
      actionSummary: `Report assigned to ${agencyContact.fullName} (${matchedCategory.agency}) under category "${matchedCategory.name}". Expected SLA: ${slaDaysFormatted}.`,
      actionSummaryKannada: `ಈ ದೂರನ್ನು ${agencyContact.fullNameKannada} ಗೆ ನಿಗದಿಪಡಿಸಲಾಗಿದೆ (${matchedCategory.kannadaSubject}). ಅಂದಾಜು ಪರಿಹಾರ ಅವಧಿ: ${slaDaysFormatted}.`
    };
  }
}
