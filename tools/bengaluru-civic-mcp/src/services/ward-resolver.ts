import { BANGALORE_WARDS, WardInfo } from '../data/civic-data.js';

export interface WardLookupResult {
  found: boolean;
  query: string;
  matchedWard?: WardInfo;
  confidence: 'exact' | 'alias' | 'pincode' | 'partial' | 'fallback';
  suggestions: string[];
}

export class WardResolver {
  /**
   * Resolves a Bengaluru locality, landmark, or PIN code to its BBMP Ward, Zone,
   * BESCOM Subdivision, and BWSSB Service Station.
   */
  static resolve(query: string): WardLookupResult {
    const cleanQuery = query.toLowerCase().trim();

    if (!cleanQuery) {
      return {
        found: false,
        query,
        confidence: 'fallback',
        suggestions: BANGALORE_WARDS.slice(0, 5).map(w => w.locality)
      };
    }

    // 1. PIN code direct match
    const pinMatch = cleanQuery.match(/\b560\d{3}\b/);
    if (pinMatch) {
      const pin = pinMatch[0];
      const match = BANGALORE_WARDS.find(w => w.pinCodes.includes(pin));
      if (match) {
        return {
          found: true,
          query,
          matchedWard: match,
          confidence: 'pincode',
          suggestions: []
        };
      }
    }

    // 2. Exact locality name match
    const exactMatch = BANGALORE_WARDS.find(
      w => w.locality.toLowerCase() === cleanQuery
    );
    if (exactMatch) {
      return {
        found: true,
        query,
        matchedWard: exactMatch,
        confidence: 'exact',
        suggestions: []
      };
    }

    // 3. Alias or landmark match
    for (const ward of BANGALORE_WARDS) {
      const hasAlias = ward.aliases.some(
        alias => alias.length >= 3 && cleanQuery.includes(alias.toLowerCase())
      );
      const hasLandmark = ward.landmarkHotspots.some(
        spot => spot.length >= 3 && cleanQuery.includes(spot.toLowerCase())
      );

      if (hasAlias || hasLandmark) {
        return {
          found: true,
          query,
          matchedWard: ward,
          confidence: 'alias',
          suggestions: []
        };
      }
    }

    // 4. Substring / partial match on locality or ward name
    const partialMatch = BANGALORE_WARDS.find(
      w => cleanQuery.includes(w.locality.toLowerCase()) ||
           w.wardName.toLowerCase().includes(cleanQuery) ||
           cleanQuery.includes(w.wardName.toLowerCase())
    );

    if (partialMatch) {
      return {
        found: true,
        query,
        matchedWard: partialMatch,
        confidence: 'partial',
        suggestions: []
      };
    }

    // 5. Fallback suggestions based on token overlap
    const tokens = cleanQuery.split(/\s+/).filter(t => t.length > 2);
    const scoredWards = BANGALORE_WARDS.map(w => {
      let score = 0;
      for (const t of tokens) {
        if (w.locality.toLowerCase().includes(t)) score += 3;
        if (w.aliases.some(a => a.includes(t))) score += 2;
        if (w.zone.toLowerCase().includes(t)) score += 1;
      }
      return { ward: w, score };
    }).filter(item => item.score > 0)
      .sort((a, b) => b.score - a.score);

    if (scoredWards.length > 0) {
      return {
        found: true,
        query,
        matchedWard: scoredWards[0].ward,
        confidence: 'partial',
        suggestions: scoredWards.slice(1, 4).map(s => s.ward.locality)
      };
    }

    // Default to central / Mahadevapura context if completely unknown
    const defaultWard = BANGALORE_WARDS.find(w => w.locality === 'Mahadevapura')!;
    return {
      found: false,
      query,
      matchedWard: defaultWard,
      confidence: 'fallback',
      suggestions: ['Mahadevapura', 'HSR Layout', 'Koramangala', 'Indiranagar', 'Whitefield', 'Hebbal']
    };
  }

  static listAllWards(): WardInfo[] {
    return BANGALORE_WARDS;
  }
}
