/**
 * Curated Bengaluru Municipal, Civic & Administrative Jurisdiction Data
 * Covering 8 BBMP Zones, 35+ major tech & residential hubs,
 * BESCOM subdivisions, BWSSB service stations, official helplines & bilingual templates.
 */

export interface WardInfo {
  locality: string;
  aliases: string[];
  wardNumber: number;
  wardName: string;
  zone: string;
  pinCodes: string[];
  mlaConstituency: string;
  bescomSubdivision: string;
  bwssbServiceStation: string;
  landmarkHotspots: string[];
}

export type CivicAgency = 'BBMP' | 'BESCOM' | 'BWSSB' | 'BTP';

export interface AgencyContact {
  agency: CivicAgency;
  fullName: string;
  fullNameKannada: string;
  primaryHelpline: string;
  whatsappBot?: string;
  twitterHandle: string;
  portalUrl: string;
  slaHours: {
    critical: number;
    moderate: number;
    standard: number;
  };
}

export interface CivicCategory {
  id: string;
  name: string;
  agency: CivicAgency;
  keywords: string[];
  kannadaSubject: string;
  kannadaKeywords: string[];
  defaultSeverity: 'critical' | 'moderate' | 'standard';
}

export const BANGALORE_WARDS: WardInfo[] = [
  // Mahadevapura Zone (Outer Ring Road & Tech Corridor)
  {
    locality: 'Mahadevapura',
    aliases: ['mahadevpura', 'mahadevapura zone', 'google ananta', 'bagmane constellation', 'ಮಹದೇವಪುರ', 'ಮಹಾದೇವಪುರ'],
    wardNumber: 82,
    wardName: 'Garudacharpalya',
    zone: 'Mahadevapura',
    pinCodes: ['560048', '560037'],
    mlaConstituency: 'Mahadevapura',
    bescomSubdivision: 'E-4 Whitefield Subdivision',
    bwssbServiceStation: 'KR Puram Central Sub-Division',
    landmarkHotspots: ['Google Ananta', 'Bagmane Constellation Park', 'Decathlon Whitefield', 'Phoenix Marketcity']
  },
  {
    locality: 'Bellandur',
    aliases: ['bellandoor', 'ecospace', 'ecoworld', 'outer ring road bellandur', 'devarabisanahalli', 'ಬೆಳ್ಳಂದೂರು', 'ಬೆಳ್ಳಂದೂರ'],
    wardNumber: 150,
    wardName: 'Bellandur',
    zone: 'Mahadevapura',
    pinCodes: ['560103', '560037'],
    mlaConstituency: 'Mahadevapura',
    bescomSubdivision: 'HSR / Bellandur O&M Unit',
    bwssbServiceStation: 'Bellandur Sewage Treatment / Water Unit',
    landmarkHotspots: ['Rmz Ecospace', 'Ecoworld', 'Bellandur Lake Gate', 'Central Mall Bellandur']
  },
  {
    locality: 'Whitefield',
    aliases: ['itpl', 'kadugodi', 'hope farm', 'channasandra', 'pattandur agrahara', 'ವೈಟ್‌ಫೀಲ್ಡ್', 'ವೈಟ್ ಫೀಲ್ಡ್'],
    wardNumber: 84,
    wardName: 'Hagadur',
    zone: 'Mahadevapura',
    pinCodes: ['560066'],
    mlaConstituency: 'Mahadevapura',
    bescomSubdivision: 'Whitefield CSD',
    bwssbServiceStation: 'Whitefield Main Sub-Division',
    landmarkHotspots: ['ITPL', 'Hope Farm Junction', 'Forum Shantiniketan', 'Kadugodi Tree Park']
  },
  {
    locality: 'Marathahalli',
    aliases: ['marathalli', 'marathahalli bridge', 'kalamandir', 'spice garden', 'ಮಾರತಹಳ್ಳಿ', 'ಮಾರತ್ತಹಳ್ಳಿ'],
    wardNumber: 85,
    wardName: 'Doddanekkundi',
    zone: 'Mahadevapura',
    pinCodes: ['560037'],
    mlaConstituency: 'Mahadevapura',
    bescomSubdivision: 'Marathahalli O&M Unit',
    bwssbServiceStation: 'HAL Service Station',
    landmarkHotspots: ['Marathahalli Bridge', 'Kalamandir Junction', 'Spice Garden', 'Multiplex Junction']
  },

  // Bommanahalli Zone (Startups & Tech Corridors)
  {
    locality: 'HSR Layout',
    aliases: ['hsr', 'hosur sarjapur road layout', 'hsr sector 1', 'hsr sector 2', 'hsr sector 3', 'hsr sector 4', 'hsr sector 6', 'hsr sector 7', '27th main', 'ಎಚ್‌ಎಸ್‌ಆರ್', 'ಹೆಚ್‌ಎಸ್‌ಆರ್', 'ಎಚ್ ಎಸ್ ಆರ್'],
    wardNumber: 174,
    wardName: 'HSR Layout',
    zone: 'Bommanahalli',
    pinCodes: ['560102'],
    mlaConstituency: 'Bommanahalli',
    bescomSubdivision: 'HSR Layout Sub-Division',
    bwssbServiceStation: 'HSR Layout Water Supply Unit',
    landmarkHotspots: ['27th Main Road', 'Agara Lake Junction', 'Silk Board Feeder', 'HSR BDA Complex']
  },
  {
    locality: 'Silk Board',
    aliases: ['central silk board', 'csb junction', 'madiwala silk board', 'ಸಿಲ್ಕ್ ಬೋರ್ಡ್'],
    wardNumber: 175,
    wardName: 'Bommanahalli',
    zone: 'Bommanahalli',
    pinCodes: ['560068'],
    mlaConstituency: 'Bommanahalli',
    bescomSubdivision: 'Bommanahalli O&M',
    bwssbServiceStation: 'Madivala Sub-Division',
    landmarkHotspots: ['Central Silk Board Flyover', 'Hosur Road Junction', 'Roopena Agrahara']
  },
  {
    locality: 'Electronic City',
    aliases: ['ecity', 'electronic city phase 1', 'electronic city phase 2', 'e-city', 'infosys gate', 'wipro gate', 'ಎಲೆಕ್ಟ್ರಾನಿಕ್ ಸಿಟಿ'],
    wardNumber: 192,
    wardName: 'Begur',
    zone: 'Bommanahalli',
    pinCodes: ['560100'],
    mlaConstituency: 'Bangalore South',
    bescomSubdivision: 'Attibele / Electronic City Unit',
    bwssbServiceStation: 'Electronic City Industrial Water Supply',
    landmarkHotspots: ['Infosys Main Gate', 'Velankani Drive', 'Wipro Electronic City Campus', 'Toll Gate Flyover']
  },
  {
    locality: 'BTM Layout',
    aliases: ['btm', 'btm 1st stage', 'btm 2nd stage', 'madiwala lake', 'kuvempunagar', 'ಬಿಟಿಎಂ', 'ಬಿಟಿಎಂ ಲೇಔಟ್'],
    wardNumber: 176,
    wardName: 'BTM Layout',
    zone: 'Bommanahalli',
    pinCodes: ['560076', '560068'],
    mlaConstituency: 'BTM Layout',
    bescomSubdivision: 'BTM 2nd Stage Unit',
    bwssbServiceStation: 'BTM Layout Service Station',
    landmarkHotspots: ['Udupi Garden Junction', 'Madiwala Lake Entrance', 'Silk Board Metro Ramp']
  },

  // South Zone (Traditional & Bustling Hubs)
  {
    locality: 'Koramangala',
    aliases: ['koramangala 1st block', 'koramangala 3rd block', 'koramangala 4th block', 'koramangala 5th block', 'koramangala 6th block', 'koramangala 7th block', 'sony world signal', 'ಕೋರಮಂಗಲ'],
    wardNumber: 151,
    wardName: 'Koramangala',
    zone: 'South',
    pinCodes: ['560034', '560095'],
    mlaConstituency: 'BTM Layout',
    bescomSubdivision: 'Koramangala CSD',
    bwssbServiceStation: 'Koramangala 4th Block Service Station',
    landmarkHotspots: ['Sony World Signal', 'Jyoti Nivas College Road', 'Forum Mall Koramangala', 'Koramangala BDA Complex']
  },
  {
    locality: 'Jayanagar',
    aliases: ['jayanagar 4th block', 'jayanagar 3rd block', 'jayanagar 9th block', 'south end circle', 'ಜಯನಗರ'],
    wardNumber: 153,
    wardName: 'Jayanagar',
    zone: 'South',
    pinCodes: ['560011', '560041'],
    mlaConstituency: 'Jayanagar',
    bescomSubdivision: 'Jayanagar CSD',
    bwssbServiceStation: 'Jayanagar 4th Block Unit',
    landmarkHotspots: ['Jayanagar 4th Block Complex', 'South End Circle', 'Cool Joint', 'Nanda Talkies Signal']
  },
  {
    locality: 'JP Nagar',
    aliases: ['jayaprakash nagar', 'jp nagar 2nd phase', 'jp nagar 6th phase', 'delmia circle', 'sarakki', 'ಜೆಪಿ ನಗರ', 'ಜೆ ಪಿ ನಗರ'],
    wardNumber: 177,
    wardName: 'JP Nagar',
    zone: 'South',
    pinCodes: ['560078'],
    mlaConstituency: 'Jayanagar',
    bescomSubdivision: 'JP Nagar Sub-Division',
    bwssbServiceStation: 'Sarakki Service Station',
    landmarkHotspots: ['Delmia Circle', 'Ranga Shankara', 'Sarakki Signal', 'Mini Forest JP Nagar']
  },
  {
    locality: 'Basavanagudi',
    aliases: ['gandhi bazaar', 'bull temple', 'davanagere benne dose basavanagudi', 'dvg road', 'ಬಸವನಗುಡಿ'],
    wardNumber: 154,
    wardName: 'Basavanagudi',
    zone: 'South',
    pinCodes: ['560004'],
    mlaConstituency: 'Basavanagudi',
    bescomSubdivision: 'Basavanagudi Unit',
    bwssbServiceStation: 'Mount Joy Water Station',
    landmarkHotspots: ['Bull Temple Road', 'Gandhi Bazaar Circle', 'Vidyarthi Bhavan Lane', 'National College Grounds']
  },

  // East Zone (CBD, Metro Spine & Historic Corridors)
  {
    locality: 'Indiranagar',
    aliases: ['100ft road indiranagar', '12th main indiranagar', 'chinmaya mission hospital road', 'cmh road', 'hal 2nd stage', 'ಇಂದಿರಾನಗರ', 'ಇಂದಿರಾ ನಗರ'],
    wardNumber: 80,
    wardName: 'Hoysala Nagar',
    zone: 'East',
    pinCodes: ['560038'],
    mlaConstituency: 'CV Raman Nagar',
    bescomSubdivision: 'Indiranagar O&M Sub-Division',
    bwssbServiceStation: 'Indiranagar 100ft Road Station',
    landmarkHotspots: ['100 Feet Road', '12th Main Food Street', 'CMH Road Metro Station', 'Indiranagar Club']
  },
  {
    locality: 'MG Road / Brigade Road / CBD',
    aliases: ['mg road', 'brigade road', 'church street', 'ashok nagar', 'cubbon park perimeter'],
    wardNumber: 111,
    wardName: 'Shantala Nagar',
    zone: 'East',
    pinCodes: ['560001', '560025'],
    mlaConstituency: 'Shantinagar',
    bescomSubdivision: 'Shivajinagar CSD',
    bwssbServiceStation: 'High Grounds Sub-Division',
    landmarkHotspots: ['Church Street Walkway', 'Brigade Road Junction', 'Trinity Circle', 'Cubbon Park Metro']
  },
  {
    locality: 'Domlur',
    aliases: ['domlur layout', 'intermediate ring road', 'irr', 'embassy golf links', 'egl'],
    wardNumber: 112,
    wardName: 'Domlur',
    zone: 'East',
    pinCodes: ['560071'],
    mlaConstituency: 'Shantinagar',
    bescomSubdivision: 'Domlur O&M Unit',
    bwssbServiceStation: 'Domlur BDA Complex Unit',
    landmarkHotspots: ['Embassy Golf Links (EGL)', 'Domlur Flyover', 'Shanti Sagar Signal Domlur']
  },

  // West Zone (Industrial, Commercial & Transit Nexus)
  {
    locality: 'Malleshwaram',
    aliases: ['malleswaram', 'sampige road', 'margosa road', 'ctr circle', '18th cross malleshwaram', 'ಮಲ್ಲೇಶ್ವರಂ', 'ಮಲ್ಲೇಶ್ವರ'],
    wardNumber: 45,
    wardName: 'Malleshwaram',
    zone: 'West',
    pinCodes: ['560003'],
    mlaConstituency: 'Malleshwaram',
    bescomSubdivision: 'Malleshwaram CSD',
    bwssbServiceStation: 'Malleshwaram 18th Cross Unit',
    landmarkHotspots: ['Sampige Road Metro', 'Margosa Road', 'CTR (Central Tiffin Room)', '18th Cross Grounds']
  },
  {
    locality: 'Rajajinagar',
    aliases: ['rajajinagar 1st block', 'navrang circle', 'orion mall perimeter', 'dr rajkumar road', 'ರಾಜಾಜಿನಗರ'],
    wardNumber: 97,
    wardName: 'Dayananda Nagar',
    zone: 'West',
    pinCodes: ['560010'],
    mlaConstituency: 'Rajajinagar',
    bescomSubdivision: 'Rajajinagar O&M Unit',
    bwssbServiceStation: 'Rajajinagar 3rd Block Station',
    landmarkHotspots: ['Navrang Circle', 'Dr Rajkumar Road', 'Orion Mall', 'ISCKON Temple Road']
  },
  {
    locality: 'Majestic / Kempegowda Bus Station',
    aliases: ['majestic', 'kbs', 'city railway station', 'sangam circle', 'subhash nagar', 'ಮೆಜೆಸ್ಟಿಕ್'],
    wardNumber: 108,
    wardName: 'Srirampura',
    zone: 'West',
    pinCodes: ['560009'],
    mlaConstituency: 'Gandhi Nagar',
    bescomSubdivision: 'Gandhi Nagar Unit',
    bwssbServiceStation: 'Majestic Central Sub-Division',
    landmarkHotspots: ['Kempegowda Metro Interchange', 'KSRTC Terminal', 'SBC Railway Station']
  },

  // Yelahanka / North Zone (Airport Corridor & Institutional Belt)
  {
    locality: 'Hebbal',
    aliases: ['hebbal flyover', 'manyata tech park', 'nagawara', 'bellary road hebbal', 'ಹೆಬ್ಬಾಳ', 'ಹೆಬ್ಬಾಳ ಫ್ಲೈಓವರ್'],
    wardNumber: 7,
    wardName: 'Byatarayanapura',
    zone: 'Yelahanka',
    pinCodes: ['560024', '560045'],
    mlaConstituency: 'Byatarayanapura',
    bescomSubdivision: 'Hebbal O&M Sub-Division',
    bwssbServiceStation: 'Hebbal Water Supply Station',
    landmarkHotspots: ['Hebbal Flyover Loops', 'Manyata Tech Park Gate 1 & 2', 'Nagawara Junction']
  },
  {
    locality: 'Yelahanka',
    aliases: ['yelahanka new town', 'yelahanka old town', 'yelahanka satellite town', 'nes ground', 'ಯಲಹಂಕ'],
    wardNumber: 4,
    wardName: 'Yelahanka Satellite Town',
    zone: 'Yelahanka',
    pinCodes: ['560064'],
    mlaConstituency: 'Yelahanka',
    bescomSubdivision: 'Yelahanka CSD',
    bwssbServiceStation: 'Yelahanka Water Board Unit',
    landmarkHotspots: ['NES Circle', 'Rail Wheel Factory Road', 'Yelahanka Lake Promenade']
  }
];

export const AGENCY_CONTACTS: Record<CivicAgency, AgencyContact> = {
  BBMP: {
    agency: 'BBMP',
    fullName: 'Bruhat Bengaluru Mahanagara Palike',
    fullNameKannada: 'ಬೃಹತ್ ಬೆಂಗಳೂರು ಮಹಾನಗರ ಪಾಲಿಕೆ',
    primaryHelpline: '080-22660000',
    whatsappBot: '+919480685700',
    twitterHandle: '@BBMPCOMM',
    portalUrl: 'https://sahaaya.bbmp.gov.in',
    slaHours: {
      critical: 24, // e.g. open manholes, cave-ins
      moderate: 72, // pothole repair, garbage dump
      standard: 168 // footpath paving, drain desilting
    }
  },
  BESCOM: {
    agency: 'BESCOM',
    fullName: 'Bangalore Electricity Supply Company Limited',
    fullNameKannada: 'ಬೆಂಗಳೂರು ವಿದ್ಯುತ್ ಸರಬರಾಜು ಕಂಪನಿ ನಿಯಮಿತ',
    primaryHelpline: '1912',
    whatsappBot: '+919449844640',
    twitterHandle: '@NammaBESCOM',
    portalUrl: 'https://bescom.karnataka.gov.in',
    slaHours: {
      critical: 4,  // live wires, transformer bursts
      moderate: 12, // persistent feeder outage
      standard: 24  // streetlights not working, billing issue
    }
  },
  BWSSB: {
    agency: 'BWSSB',
    fullName: 'Bangalore Water Supply and Sewerage Board',
    fullNameKannada: 'ಬೆಂಗಳೂರು ನೀರು ಸರಬರಾಜು ಮತ್ತು ಒಳಚರಂಡಿ ಮಂಡಳಿ',
    primaryHelpline: '1916',
    whatsappBot: '+918762228888',
    twitterHandle: '@BWSSBOnline',
    portalUrl: 'https://bwssb.karnataka.gov.in',
    slaHours: {
      critical: 8,  // sewage backup into homes, main pipeline rupture
      moderate: 24, // pipeline leak, zero drinking water pressure
      standard: 48  // clogged stormwater valve, meter test
    }
  },
  BTP: {
    agency: 'BTP',
    fullName: 'Bengaluru Traffic Police',
    fullNameKannada: 'ಬೆಂಗಳೂರು ನಗರ ಸಂಚಾರ ಪೊಲೀಸ್',
    primaryHelpline: '1095',
    whatsappBot: '+919480801000',
    twitterHandle: '@blrcitytraffic',
    portalUrl: 'https://btp.gov.in',
    slaHours: {
      critical: 1,  // non-functional junction signal creating gridlock
      moderate: 6,  // hazardous breakdown vehicle blocking lane
      standard: 24  // illegal parking / footpath encroachment report
    }
  }
};

export const CIVIC_CATEGORIES: CivicCategory[] = [
  {
    id: 'pothole_road',
    name: 'Road Damage & Potholes',
    agency: 'BBMP',
    keywords: ['pothole', 'gundi', 'broken road', 'asphalt', 'crater', 'bad road', 'tar', 'resurfacing', 'uneven road', 'manhole cover'],
    kannadaSubject: 'ರಸ್ತೆ ಗುಂಡಿ ಮತ್ತು ಹಾಳಾದ ರಸ್ತೆ ದುರಸ್ತಿ ಕೋರಿಕೆ',
    kannadaKeywords: ['ರಸ್ತೆ ಗುಂಡಿ', 'ಹಾಳಾದ ರಸ್ತೆ', 'ಗುಂಡಿಗಳು', 'ಡಾಂಬರು'],
    defaultSeverity: 'moderate'
  },
  {
    id: 'solid_waste_garbage',
    name: 'Garbage & Solid Waste Management',
    agency: 'BBMP',
    keywords: ['garbage', 'kasa', 'waste', 'trash', 'debris', 'black spot', 'dumping', 'smell', 'litter', 'pourakarmika'],
    kannadaSubject: 'ಕಸ ವಿಲೇವಾರಿ ಮತ್ತು ಸಾರ್ವಜನಿಕ ನೈರ್ಮಲ್ಯ ರಕ್ಷಣೆ ಕೋರಿಕೆ',
    kannadaKeywords: ['ಕಸ ವಿಲೇವಾರಿ', 'ತ್ಯಾಜ್ಯ', 'ಕಸದ ತೊಟ್ಟಿ', 'ಸ್ವಚ್ಛತೆ'],
    defaultSeverity: 'moderate'
  },
  {
    id: 'storm_water_drain',
    name: 'Stormwater Drains & Waterlogging',
    agency: 'BBMP',
    keywords: ['drain', 'waterlogging', 'flooding', 'rajakaluve', 'stormwater', 'overflowing gutter', 'rainwater choke', 'water accumulation'],
    kannadaSubject: 'ಮಳೆನೀರು ಚರಂಡಿ ಸ್ವಚ್ಛತೆ ಮತ್ತು ನೀರು ನಿಲ್ಲುವ ಸಮಸ್ಯೆ ನಿವಾರಣೆ ಕೋರಿಕೆ',
    kannadaKeywords: ['ಮಳೆನೀರು ಚರಂಡಿ', 'ರಾಜಕಾಲುವೆ', 'ನೀರು ನಿಲ್ಲುವುದು', 'ಪ್ರವಾಹ'],
    defaultSeverity: 'critical'
  },
  {
    id: 'streetlight_electrical',
    name: 'Streetlight Failure & Electrical Hazards',
    agency: 'BESCOM',
    keywords: ['streetlight', 'street light', 'dark road', 'sparking', 'hanging wire', 'broken pole', 'bulb off', 'lamp post'],
    kannadaSubject: 'ಬೀದಿದೀಪ ದುರಸ್ತಿ ಮತ್ತು ವಿದ್ಯುತ್ ಸುರಕ್ಷತಾ ಕ್ರಮ ಕೋರಿಕೆ',
    kannadaKeywords: ['ಬೀದಿದೀಪ', 'ಕತ್ತಲೆ ರಸ್ತೆ', 'ವಿದ್ಯುತ್ ತಂತಿ', 'ಬೆಳಕಿನ ಕೊರತೆ'],
    defaultSeverity: 'standard'
  },
  {
    id: 'power_outage',
    name: 'Frequent Power Cut & Low Voltage',
    agency: 'BESCOM',
    keywords: ['power cut', 'electricity outage', 'load shedding', 'transformer trip', 'voltage fluctuation', 'current illa', 'no power'],
    kannadaSubject: 'ನಿರಂತರ ವಿದ್ಯುತ್ ಕಡಿತ ಮತ್ತು ವೋಲ್ಟೇಜ್ ಸಮಸ್ಯೆ ಪರಿಹಾರ ಕೋರಿಕೆ',
    kannadaKeywords: ['ವಿದ್ಯುತ್ ಕಡಿತ', 'ಕರೆಂಟ್ ಇಲ್ಲ', 'ಟ್ರಾನ್ಸ್‌ಫಾರ್ಮರ್', 'ಲೋ ವೋಲ್ಟೇಜ್'],
    defaultSeverity: 'moderate'
  },
  {
    id: 'water_leakage_contamination',
    name: 'Drinking Water Pipeline Leak / Contamination',
    agency: 'BWSSB',
    keywords: ['water leak', 'pipe burst', 'kaveri water', 'dirty water', 'muddy water', 'drinking water', 'pipeline broken', 'no water supply'],
    kannadaSubject: 'ಕಾವೇರಿ ನೀರು ಸರಬರಾಜು ಪೈಪ್‌ಲೈನ್ ಸೋರಿಕೆ ಮತ್ತು ಶುದ್ಧ ನೀರಿನ ಕೊರತೆ',
    kannadaKeywords: ['ನೀರು ಸೋರಿಕೆ', 'ಕಾವೇರಿ ನೀರು', 'ಕಲುಷಿತ ನೀರು', 'ಪೈಪ್ ಒಡೆದಿರುವುದು'],
    defaultSeverity: 'critical'
  },
  {
    id: 'sewage_overflow',
    name: 'Sewage Overflow & Blocked Sanitary Line',
    agency: 'BWSSB',
    keywords: ['sewage', 'drain water in house', 'manhole overflowing', 'smelly sewage', 'sanitary line block', 'toilet backflow'],
    kannadaSubject: 'ಒಳಚರಂಡಿ ನೀರು ಉಕ್ಕಿ ಹರಿಯುವುದು ಮತ್ತು ನೈರ್ಮಲ್ಯ ಸಮಸ್ಯೆ ಪರಿಹಾರ',
    kannadaKeywords: ['ಒಳಚರಂಡಿ', 'ಮ್ಯಾನ್‌ಹೋಲ್', 'ಚರಂಡಿ ನೀರು', 'ದುರ್ವಾಸನೆ'],
    defaultSeverity: 'critical'
  },
  {
    id: 'traffic_signal_hazard',
    name: 'Traffic Signal Malfunction & Hazard',
    agency: 'BTP',
    keywords: ['traffic signal', 'signal not working', 'junction jam', 'broken signal', 'traffic police', 'pedestrian hazard', 'illegal parking'],
    kannadaSubject: 'ಸಂಚಾರ ಸಿಗ್ನಲ್ ದೋಷ ಮತ್ತು ಸಾರ್ವಜನಿಕ ಸುರಕ್ಷತಾ ಕ್ರಮ',
    kannadaKeywords: ['ಟ್ರಾಫಿಕ್ ಸಿಗ್ನಲ್', 'ಸಿಗ್ನಲ್ ಆಫ್', 'ಸಂಚಾರ ದಟ್ಟಣೆ', 'ಪಾದಚಾರಿ ಸಮಸ್ಯೆ'],
    defaultSeverity: 'moderate'
  }
];

export const KANGLISH_PHRASES = [
  { phrase: 'Current illa', meaning: 'There is no power / electricity', agency: 'BESCOM' },
  { phrase: 'Neeru barthilla', meaning: 'Water is not coming / no water supply', agency: 'BWSSB' },
  { phrase: 'Raste thumba gundi ide', meaning: 'The road is full of potholes', agency: 'BBMP' },
  { phrase: 'Kasa etthilla', meaning: 'Garbage has not been picked up', agency: 'BBMP' },
  { phrase: 'Swalpa bega sari maadi', meaning: 'Please fix this quickly / urgently', agency: 'BBMP' }
];
