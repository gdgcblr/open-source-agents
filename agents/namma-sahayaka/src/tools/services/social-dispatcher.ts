import { WardInfo, AgencyContact, CivicCategory } from '../data/civic-data.js';

export interface DispatchPackage {
  tweetText: string;
  tweetLength: number;
  twitterHandles: string[];
  hashtags: string[];
  helplineNumber: string;
  whatsappBotNumber?: string;
  whatsappMessageTemplate: string;
  portalSubmissionUrl: string;
  escalationChecklist: string[];
}

export class SocialDispatcher {
  /**
   * Generates formatted public escalation posts for X/Twitter, WhatsApp, and helpline contacts.
   */
  static generateDispatch(params: {
    ward: WardInfo;
    agencyContact: AgencyContact;
    category: CivicCategory;
    description: string;
    landmark?: string;
  }): DispatchPackage {
    const loc = params.landmark
      ? `${params.landmark}, ${params.ward.locality}`
      : params.ward.locality;

    const handles = [params.agencyContact.twitterHandle];
    if (params.agencyContact.agency === 'BBMP') {
      handles.push('@BBMP_MAYOR');
    }

    const hashtags = [
      '#NammaBengaluru',
      '#BengaluruCivic',
      `#Ward${params.ward.wardNumber}`,
      `#${params.ward.locality.replace(/[^a-zA-Z0-9]/g, '')}`
    ];

    // Construct a high-impact, clean tweet under 270 chars
    // Format: @Handle Urgent issue at [Locality] (Ward [No]): [Brief issue]. Please resolve! [Hashtags]
    const shortDesc = params.description.length > 90
      ? `${params.description.slice(0, 87)}...`
      : params.description;

    const tagStr = handles.join(' ');
    const hashStr = hashtags.slice(0, 3).join(' ');
    let tweet = `${tagStr} Urgent attention required at ${loc} (Ward ${params.ward.wardNumber}, ${params.ward.zone} Zone): ${shortDesc}. Please inspect and resolve! ${hashStr}`;

    if (tweet.length > 275) {
      const excess = tweet.length - 275;
      const trimmedDesc = shortDesc.slice(0, Math.max(20, shortDesc.length - excess - 4)) + '...';
      tweet = `${tagStr} Civic issue at ${loc} (Ward ${params.ward.wardNumber}): ${trimmedDesc}. Pls resolve! ${hashStr}`;
    }

    const waTemplate = `Hello ${params.agencyContact.agency} Helpdesk, I wish to register a grievance regarding ${params.category.name} at ${loc} (Ward No. ${params.ward.wardNumber}, ${params.ward.zone}). Issue: ${params.description}. Please register and share ticket number.`;

    const escalationChecklist = [
      `1. Lodge ticket on official portal (${params.agencyContact.portalUrl}) or call ${params.agencyContact.primaryHelpline} to get an official docket/ticket ID.`,
      `2. Save the docket ID. If field team does not visit within ${params.agencyContact.slaHours[params.category.defaultSeverity]} hours, escalate via WhatsApp: ${params.agencyContact.whatsappBot || params.agencyContact.primaryHelpline}.`,
      `3. Post the generated tweet tagging ${params.agencyContact.twitterHandle} with your ticket ID and photo evidence.`,
      `4. Next level escalation: Contact the ${params.ward.mlaConstituency} MLA grievance cell and BBMP Zonal Joint Commissioner for ${params.ward.zone} Zone.`
    ];

    return {
      tweetText: tweet,
      tweetLength: tweet.length,
      twitterHandles: handles,
      hashtags,
      helplineNumber: params.agencyContact.primaryHelpline,
      whatsappBotNumber: params.agencyContact.whatsappBot,
      whatsappMessageTemplate: waTemplate,
      portalSubmissionUrl: params.agencyContact.portalUrl,
      escalationChecklist
    };
  }
}
