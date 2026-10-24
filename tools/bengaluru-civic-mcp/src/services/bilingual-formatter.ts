import { WardInfo, AgencyContact, CivicCategory } from '../data/civic-data.js';

export interface BilingualComplaintResult {
  referenceId: string;
  generatedDate: string;
  english: {
    toAuthority: string;
    subject: string;
    body: string;
    locationSummary: string;
    expectedResolution: string;
  };
  kannada: {
    toAuthority: string;
    subject: string;
    body: string;
    locationSummary: string;
    expectedResolution: string;
  };
}

export class BilingualFormatter {
  /**
   * Generates formal administrative grievance letters in both English and Kannada.
   */
  static generate(params: {
    ward: WardInfo;
    agencyContact: AgencyContact;
    category: CivicCategory;
    description: string;
    landmark?: string;
    citizenName?: string;
    contactNumber?: string;
  }): BilingualComplaintResult {
    const today = new Date().toISOString().split('T')[0];
    const refCode = `BLR-${params.category.agency}-${params.ward.wardNumber}-${Math.floor(1000 + Math.random() * 9000)}`;
    const citizen = params.citizenName || 'A Concerned Resident of Bengaluru';
    const citizenKannada = params.citizenName || 'ಜಾಗೃತ ಬೆಂಗಳೂರು ನಿವಾಸಿ';
    const locationDetail = params.landmark
      ? `${params.landmark}, ${params.ward.locality} (Ward ${params.ward.wardNumber}: ${params.ward.wardName}, Zone: ${params.ward.zone})`
      : `${params.ward.locality} (Ward ${params.ward.wardNumber}: ${params.ward.wardName}, Zone: ${params.ward.zone})`;

    // English Formatter
    const englishSubject = `URGENT: Redressal for ${params.category.name} at ${params.ward.locality} (Ward No. ${params.ward.wardNumber})`;
    const englishBody = `To:
The Executive Engineer / Competent Officer,
${params.agencyContact.fullName} (${params.agencyContact.agency}),
Bengaluru, Karnataka.

Date: ${today}
Grievance Ref: ${refCode}

Subject: ${englishSubject}

Respected Sir/Madam,

I am writing to formally lodge a public civic grievance regarding an ongoing issue within your jurisdiction.

Location Details:
- Locality / Landmark: ${params.landmark || params.ward.locality}
- Ward: No. ${params.ward.wardNumber} (${params.ward.wardName})
- Zone: ${params.ward.zone}
- MLA Constituency: ${params.ward.mlaConstituency}
- Operational Unit: ${params.agencyContact.agency === 'BESCOM' ? params.ward.bescomSubdivision : params.agencyContact.agency === 'BWSSB' ? params.ward.bwssbServiceStation : 'BBMP Engineering Division'}

Issue Description:
${params.description}

Public Impact & Urgency:
This condition is causing severe inconvenience, safety hazards, and disruptions to local residents, commuters, and school-going children. Immediate inspection and engineering intervention are requested.

Kindly register this complaint, issue an acknowledgement ticket, and dispatch a field team in accordance with the Citizen Charter SLA.

Yours faithfully,
${citizen}
${params.contactNumber ? `Contact: ${params.contactNumber}` : ''}
Bengaluru, Karnataka`;

    // Kannada Formatter (Authentic Administrative Kannada)
    const kannadaSubject = `ತುರ್ತು ಮನವಿ: ವಾರ್ಡ್ ಸಂಖ್ಯೆ ${params.ward.wardNumber} (${params.ward.wardName}), ${params.ward.locality} ವ್ಯಾಪ್ತಿಯಲ್ಲಿ ${params.category.kannadaSubject}`;
    const kannadaBody = `ಗೆ:
ಕಾರ್ಯಪಾಲಕ ಅಭಿಯಂತರರು / ಸಂಬಂಧಪಟ್ಟ ಅಧಿಕಾರಿಗಳು,
${params.agencyContact.fullNameKannada} (${params.agencyContact.agency}),
ಬೆಂಗಳೂರು, ಕರ್ನಾಟಕ.

ದಿನಾಂಕ: ${today}
ದೂರು ಉಲ್ಲೇಖ ಸಂಖ್ಯೆ: ${refCode}

ವಿಷಯ: ${kannadaSubject}

ಮಾನ್ಯರೇ,

ಮೇಲ್ಕಂಡ ವಿಷಯಕ್ಕೆ ಸಂಬಂಧಿಸಿದಂತೆ, ನಾನು ತಮ್ಮ ಘನತೆವೆತ್ತ ಕಚೇರಿಯ ವ್ಯಾಪ್ತಿಯಲ್ಲಿ ಕಂಡುಬಂದಿರುವ ಸಾರ್ವಜನಿಕ ಸಮಸ್ಯೆಯ ಬಗ್ಗೆ ಈ ಮೂಲಕ ಲಿಖಿತ ದೂರು ಸಲ್ಲಿಸುತ್ತಿದ್ದೇನೆ.

ಸ್ಥಳದ ವಿವರಗಳು:
- ನಿರ್ದಿಷ್ಟ ಸ್ಥಳ / ಪ್ರಮುಖ ಗುರುತು: ${params.landmark || params.ward.locality}
- ವಾರ್ಡ್ ವಿವರ: ಸಂಖ್ಯೆ ${params.ward.wardNumber} (${params.ward.wardName})
- ವಲಯ: ${params.ward.zone}
- ವಿಧಾನಸಭಾ ಕ್ಷೇತ್ರ: ${params.ward.mlaConstituency}
- ಸಂಬಂಧಪಟ್ಟ ವಿಭಾಗ: ${params.agencyContact.agency === 'BESCOM' ? params.ward.bescomSubdivision : params.agencyContact.agency === 'BWSSB' ? params.ward.bwssbServiceStation : 'ಬಿಬಿಎಂಪಿ ಎಂಜಿನಿಯರಿಂಗ್ ವಿಭಾಗ'}

ಸಮಸ್ಯೆಯ ವಿವರ:
${params.description}

ಸಾರ್ವಜನಿಕ ಹಿತಾಸಕ್ತಿ ಮತ್ತು ಪರಿಣಾಮ:
ಈ ಗಂಭೀರ ಸಮಸ್ಯೆಯಿಂದಾಗಿ ಸ್ಥಳೀಯ ನಾಗರಿಕರು, ಹಿರಿಯರು, ಪಾದಚಾರಿಗಳು ಹಾಗೂ ವಾಹನ ಸವಾರರು ತೀವ್ರ ತೊಂದರೆ ಅನುಭವಿಸುತ್ತಿದ್ದಾರೆ. ಅಪಘಾತ ಹಾಗೂ ನೈರ್ಮಲ್ಯ ಹಾನಿಯ ಭೀತಿ ಎದುರಾಗಿದೆ.

ಆದ್ದರಿಂದ, ದಯವಿಟ್ಟು ಈ ದೂರನ್ನು ಸ್ವೀಕರಿಸಿ, ಸ್ಥಳಕ್ಕೆ ಅಧಿಕಾರಿಗಳ ತಂಡವನ್ನು ರವಾನಿಸಿ ಶೀಘ್ರವಾಗಿ ಪರಿಹಾರ ಒದಗಿಸಬೇಕಾಗಿ ವಿನಂತಿಸಿಕೊಳ್ಳುತ್ತೇನೆ.

ಧನ್ಯವಾದಗಳೊಂದಿಗೆ,
ತಮ್ಮ ವಿಶ್ವಾಸಿ,
${citizenKannada}
${params.contactNumber ? `ದೂರವಾಣಿ: ${params.contactNumber}` : ''}
ಬೆಂಗಳೂರು`;

    return {
      referenceId: refCode,
      generatedDate: today,
      english: {
        toAuthority: `${params.agencyContact.fullName} (${params.agencyContact.agency})`,
        subject: englishSubject,
        body: englishBody,
        locationSummary: locationDetail,
        expectedResolution: `Standard SLA: ${params.agencyContact.slaHours[params.category.defaultSeverity]} hours via ${params.agencyContact.portalUrl}`
      },
      kannada: {
        toAuthority: `${params.agencyContact.fullNameKannada} (${params.agencyContact.agency})`,
        subject: kannadaSubject,
        body: kannadaBody,
        locationSummary: locationDetail,
        expectedResolution: `ಪರಿಹಾರ ಕಾಲಾವಧಿ: ${params.agencyContact.slaHours[params.category.defaultSeverity]} ಗಂಟೆಗಳು (${params.agencyContact.portalUrl})`
      }
    };
  }
}
