"""
Target Application Repository: Auction Service (Buggy Implementation - MASTER BACKUP)
Used for resetting demo state during live stage demonstrations.
"""

import sqlite3
from typing import List, Dict, Any

def fetch_active_auctions_with_bids(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """
    Fetches all active auctions and their corresponding bids.
    
    WARNING: THIS IS AN INTENTIONALLY UNOPTIMIZED IMPLEMENTATION
    THAT REPRODUCES AN N+1 QUERY STORM IN PRE-PROD ENVIRONMENTS.
    """
    cursor = conn.cursor()
    
    # Query 1: Fetch 40 active auctions
    cursor.execute("""
        SELECT id, title, status, reserve_price, created_at
        FROM auctions
        WHERE status = 'ACTIVE'
        ORDER BY id ASC
        LIMIT 40
    """)
    auctions = cursor.fetchall()
    
    results = []
    # Queries 2..41: Query storm! Iterating and firing individual SELECT statements
    for auction in auctions:
        auction_id = auction[0]
        
        # SINFUL N+1 QUERY: Unindexed lookup scanning entire bids table (50,000 rows)
        cursor.execute("""
            SELECT id, bidder_name, amount, bid_time
            FROM bids
            WHERE auction_id = ?
            ORDER BY amount DESC
        """, (auction_id,))
        bids = cursor.fetchall()
        
        results.append({
            "auction_id": auction_id,
            "title": auction[1],
            "status": auction[2],
            "reserve_price": auction[3],
            "created_at": auction[4],
            "bids_count": len(bids),
            "top_bid": bids[0][2] if bids else None,
            "bids": bids
        })
        
    return results
