"""
NammaRaktha - Mobile-First Emergency Blood & Platelet Dispatch.
Optimized for one-handed thumb use during hospital emergencies in Bengaluru.
Built with accessible typography, WCAG contrast, minimal professional WhatsApp templates,
and 1-tap Twitter / X broadcast.
Runs on http://localhost:8081.
"""

import json
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from .config import PORT, HOST
from .agent import agent
from .blood_banks import BENGALURU_BLOOD_BANKS
from .db import add_donor, get_all_donors_count, get_recent_emergencies, accept_emergency

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <circle cx="16" cy="16" r="15" fill="#fce8e6" stroke="#f5c2c7" stroke-width="0.5"/>
  <path d="M16 5 C16 5 8 15 8 20 C8 24.42 11.58 28 16 28 C20.42 28 24 24.42 24 20 C24 15 16 5 16 5 Z" fill="#d93025"/>
  <ellipse cx="12" cy="16" rx="1.2" ry="2.2" transform="rotate(-30 12 16)" fill="#ffffff" opacity="0.4"/>
  <rect x="14.5" y="17" width="3" height="7" rx="1" fill="#ffffff"/>
  <rect x="12.5" y="19" width="7" height="3" rx="1" fill="#ffffff"/>
</svg>"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>NammaRaktha • Google Crisis Response • Bengaluru</title>
  
  <!-- Favicon -->
  <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='15' fill='%23fce8e6' stroke='%23f5c2c7' stroke-width='0.5'/%3E%3Cpath d='M16 5 C16 5 8 15 8 20 C8 24.42 11.58 28 16 28 C20.42 28 24 24.42 24 20 C24 15 16 5 16 5 Z' fill='%23d93025'/%3E%3Cellipse cx='12' cy='16' rx='1.2' ry='2.2' transform='rotate(-30 12 16)' fill='%23ffffff' opacity='0.4'/%3E%3Crect x='14.5' y='17' width='3' height='7' rx='1' fill='%23ffffff'/%3E%3Crect x='12.5' y='19' width='7' height='3' rx='1' fill='%23ffffff'/%3E%3C/svg%3E">
  <link rel="alternate icon" href="/favicon.ico">
  
  <!-- Google Fonts: Google Sans & Roboto -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Google+Sans:wght@400;500;700&family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
  
  <!-- Google Material Symbols Outlined -->
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200" />
  
  <!-- FontAwesome Backup -->
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  
  <!-- Tailwind CSS -->
  <script src="https://cdn.tailwindcss.com"></script>
  
  <style>
    :root {
      --md-sys-color-primary: #0b57d0;
      --md-sys-color-surface: #f8fafd;
      --md-sys-color-surface-container: #ffffff;
      --md-sys-color-outline: #74777f;
    }
    body {
      font-family: 'Google Sans', 'Roboto', -apple-system, BlinkMacSystemFont, sans-serif;
      background-color: #f8fafd;
      color: #1f1f1f;
      -webkit-tap-highlight-color: transparent;
    }
    .material-symbols-outlined {
      font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
      vertical-align: middle;
    }
    .material-symbols-fill {
      font-variation-settings: 'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 24;
      vertical-align: middle;
    }
    .no-scrollbar::-webkit-scrollbar {
      display: none;
    }
    .no-scrollbar {
      -ms-overflow-style: none;
      scrollbar-width: none;
    }
    .m3-card {
      background: #ffffff;
      border: 1px solid #e0e2ec;
      border-radius: 24px;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
      transition: all 0.2s ease;
    }
    .m3-chip {
      border: 1px solid #c4c7c5;
      background-color: #ffffff;
      color: #1f1f1f;
      border-radius: 9999px;
      transition: all 0.15s ease;
    }
    .m3-chip:hover {
      background-color: #f1f3f4;
    }
    .m3-btn-primary {
      background-color: #0b57d0;
      color: #ffffff;
      border-radius: 9999px;
      transition: all 0.2s ease;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
    }
    .m3-btn-primary:hover {
      background-color: #0842a0;
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.16);
    }
  </style>
</head>
<body class="min-h-screen flex flex-col pb-24 md:pb-10 antialiased">

  <!-- Google Product App Bar -->
  <header class="bg-white border-b border-[#e0e2ec] sticky top-0 z-40">
    <div class="max-w-2xl mx-auto px-4 py-3 flex justify-between items-center">
      <div class="flex items-center space-x-3">
        <div class="relative w-10 h-10 rounded-2xl bg-[#fce8e6] flex items-center justify-center text-[#d93025] shadow-sm">
          <span class="material-symbols-outlined text-2xl text-[#d93025] material-symbols-fill">bloodtype</span>
          <span class="absolute -top-1 -right-1 w-3 h-3 bg-[#1e8e3e] border-2 border-white rounded-full"></span>
        </div>
        <div>
          <div class="flex items-center space-x-1.5">
            <h1 class="text-xl font-bold tracking-tight text-[#1f1f1f]">NammaRaktha</h1>
            <span class="text-[10px] font-medium bg-[#e8f0fe] text-[#0b57d0] px-2 py-0.5 rounded-full">Crisis Response</span>
          </div>
          <p class="text-xs text-[#444746] font-medium">Bengaluru Emergency Blood & Platelet Network</p>
        </div>
      </div>
      
      <button onclick="openDonorModal()" class="rounded-full bg-[#d3e3fd] hover:bg-[#c2d7fc] text-[#041e49] font-medium text-xs px-3.5 py-2 transition flex items-center gap-1.5 shadow-sm">
        <span class="material-symbols-outlined text-base">person_add</span>
        <span>Register</span>
      </button>
    </div>
  </header>

  <!-- Main Container -->
  <main class="flex-1 max-w-2xl w-full mx-auto px-4 py-4 space-y-4">

    <!-- Emergency Dispatch Banner -->
    <div class="bg-[#d93025] text-white rounded-2xl p-3.5 shadow-sm flex items-center justify-between">
      <div class="flex items-center gap-3">
        <span class="material-symbols-outlined text-white text-2xl material-symbols-fill">emergency</span>
        <div>
          <div class="text-[10px] font-bold tracking-wider uppercase opacity-90">Emergency Blood & Platelet Dispatch</div>
          <div class="text-xs md:text-sm font-medium">Bengaluru 24/7 NBTC-Certified Blood Centers</div>
        </div>
      </div>
      <span class="bg-white/20 backdrop-blur-sm text-[11px] font-medium px-2.5 py-1 rounded-full text-white flex items-center gap-1 shrink-0">
        <span class="material-symbols-outlined text-xs">verified</span> Live
      </span>
    </div>

    <!-- Requisition Input Card -->
    <div class="m3-card p-5">
      <div class="flex justify-between items-center mb-2.5">
        <label for="rawInput" class="text-xs font-bold uppercase tracking-wider text-[#444746] flex items-center gap-1.5">
          <span class="material-symbols-outlined text-base text-[#0b57d0]">notes</span>
          Emergency Patient Requisition
        </label>
        <span class="text-[11px] font-medium text-[#137333] bg-[#e6f4ea] px-2.5 py-0.5 rounded-full flex items-center gap-1">
          <span class="w-1.5 h-1.5 rounded-full bg-[#1e8e3e]"></span> AI Clinical Triage
        </span>
      </div>

      <!-- Sample Chips -->
      <div class="mb-3">
        <div class="text-[11px] font-medium text-[#444746] mb-1.5 flex items-center gap-1">
          <span class="material-symbols-outlined text-sm text-[#ea8600]">bolt</span>
          <span>Sample Emergency Cases:</span>
        </div>
        <div class="flex items-center gap-2 overflow-x-auto no-scrollbar pb-1 text-xs font-medium">
          <button onclick="handleCaseSelect('manipal')" class="m3-chip shrink-0 px-3 py-1.5 flex items-center gap-1.5 text-xs">
            <span class="w-2 h-2 rounded-full bg-[#d93025]"></span> Manipal • A+ Platelets (Dengue)
          </button>
          <button onclick="handleCaseSelect('victoria')" class="m3-chip shrink-0 px-3 py-1.5 flex items-center gap-1.5 text-xs">
            <span class="w-2 h-2 rounded-full bg-[#d93025]"></span> Victoria BMCRI • O- Blood (Accident)
          </button>
          <button onclick="handleCaseSelect('kidwai')" class="m3-chip shrink-0 px-3 py-1.5 flex items-center gap-1.5 text-xs">
            <span class="w-2 h-2 rounded-full bg-[#0b57d0]"></span> Kidwai • B+ SDP (Leukemia)
          </button>
          <button onclick="handleCaseSelect('jayadeva')" class="m3-chip shrink-0 px-3 py-1.5 flex items-center gap-1.5 text-xs">
            <span class="w-2 h-2 rounded-full bg-[#b3261e]"></span> Jayadeva • Bombay Blood (ICU)
          </button>
        </div>
      </div>

      <!-- Textarea -->
      <div class="relative">
        <textarea id="rawInput" rows="3" class="w-full bg-white border border-[#74777f]/40 rounded-2xl p-3.5 text-sm font-medium text-[#1f1f1f] placeholder-[#74777f] focus:outline-none focus:border-[#0b57d0] focus:ring-4 focus:ring-[#0b57d0]/10 transition" placeholder="e.g. Urgent need 2 units A+ platelets for dengue patient at Manipal Hospital Old Airport Rd, contact Suresh 9886012345..."></textarea>
      </div>

      <!-- Search Button -->
      <button id="triageBtn" onclick="runTriage()" class="w-full mt-3.5 py-3.5 m3-btn-primary font-medium text-sm flex items-center justify-center gap-2">
        <span class="material-symbols-outlined text-xl">search</span>
        <span>Find Compatible Donors & Blood Banks</span>
      </button>
    </div>

    <!-- Guardrail Alert -->
    <div id="guardrailAlert" class="hidden m3-card bg-[#fce8e6] border-[#f5c2c7] p-5">
      <div class="flex items-start gap-3">
        <span class="material-symbols-outlined text-[#d93025] text-2xl shrink-0 material-symbols-fill">report</span>
        <div>
          <h3 class="text-sm font-bold text-[#601410]">Unable to Dispatch Requisition</h3>
          <p id="guardrailText" class="text-xs text-[#601410] font-medium mt-1 leading-snug"></p>
        </div>
      </div>
    </div>

    <!-- Missing Info Validation Banner -->
    <div id="validationBanner" class="hidden m3-card bg-[#fef7e0] border-[#fde68a] p-4">
      <div class="flex items-start gap-2.5">
        <span class="material-symbols-outlined text-[#ea8600] text-xl shrink-0 material-symbols-fill">warning</span>
        <div class="w-full">
          <h3 class="text-xs font-bold text-[#7c2d12]">Incomplete Requisition Details:</h3>
          <ul id="warningsList" class="mt-1 space-y-1 text-xs font-medium text-[#7c2d12]"></ul>
        </div>
      </div>
    </div>

    <!-- Results Section -->
    <div id="resultsWrapper" class="hidden space-y-4">

      <!-- Case Header Card -->
      <div class="m3-card p-5 border-l-4 border-l-[#d93025]">
        <div class="flex items-center space-x-2 mb-2">
          <span id="urgencyBadge" class="px-2.5 py-0.5 bg-[#fce8e6] text-[#b3261e] border border-[#f5c2c7] font-bold text-[11px] rounded-full uppercase">CRITICAL</span>
          <span id="caseTitle" class="text-lg font-bold text-[#1f1f1f]">A+ Platelets • 2 Units</span>
        </div>
        <p id="caseLocation" class="text-sm font-medium text-[#1f1f1f] flex items-center gap-1.5">
          <span class="material-symbols-outlined text-[#d93025] text-base material-symbols-fill">location_on</span>
          <span>Manipal Hospital, Old Airport Road</span>
        </p>
        <p class="text-xs font-medium text-[#444746] mt-1.5 flex items-center gap-1">
          <span class="material-symbols-outlined text-sm text-[#444746]">call</span>
          Attendant: <strong id="caseContact" class="text-[#1f1f1f] font-bold ml-1">Suresh (+91 98860 12345)</strong>
        </p>
      </div>

      <!-- Compatible Donors Card -->
      <div class="m3-card p-5">
        <span class="text-xs font-bold uppercase tracking-wider text-[#444746] block mb-2 flex items-center gap-1.5">
          <span class="material-symbols-outlined text-base text-[#0b57d0]">sync_alt</span>
          Compatible Donor Blood Groups
        </span>
        <div id="donorPills" class="flex flex-wrap gap-2 mb-2.5"></div>
        <div id="clinicalRuleBox" class="p-3 rounded-2xl bg-[#f0f4f9] border border-[#d3e3fd] text-xs font-medium text-[#041e49] leading-relaxed flex items-start gap-2"></div>
      </div>

      <!-- Top Blood Centre Action Card -->
      <div class="m3-card p-5 border-l-4 border-l-[#0b57d0]">
        <div class="flex justify-between items-start mb-2">
          <div>
            <span class="text-[10px] font-bold uppercase tracking-wider text-[#0b57d0] bg-[#e8f0fe] px-2.5 py-0.5 rounded-full">
              Recommended 24/7 Blood Centre
            </span>
            <h3 id="topBankName" class="text-base font-bold text-[#1f1f1f] mt-1">Rotary TTK Blood Centre (BMST)</h3>
            <p id="topBankArea" class="text-xs font-medium text-[#444746] mt-0.5 flex items-center gap-1">
              <span class="material-symbols-outlined text-sm text-[#1e8e3e]">directions_subway</span>
              <span>Indiranagar • ~1.8 km from Metro</span>
            </p>
          </div>
        </div>
        <p id="topBankTransit" class="text-xs font-medium text-[#7c2d12] bg-[#fef7e0] p-2.5 rounded-xl border border-[#fde68a] mb-3 flex items-start gap-1.5"></p>
        
        <div class="flex gap-2">
          <a id="topBankCall" href="#" class="flex-1 py-2.5 m3-btn-primary font-medium text-xs text-center flex items-center justify-center gap-1.5">
            <span class="material-symbols-outlined text-base">call</span>
            <span>Call Blood Centre</span>
          </a>
          <a id="topBankMap" href="#" target="_blank" class="px-4 py-2.5 rounded-full border border-[#74777f]/40 hover:bg-[#f1f3f4] text-[#0b57d0] font-medium text-xs flex items-center justify-center gap-1">
            <span class="material-symbols-outlined text-base">directions</span>
            <span class="hidden sm:inline">Directions</span>
          </a>
        </div>
      </div>

      <!-- Matched Community Donors -->
      <div class="m3-card p-5">
        <div class="flex justify-between items-center mb-2.5">
          <span class="text-xs font-bold uppercase tracking-wider text-[#444746] flex items-center gap-1.5">
            <span class="material-symbols-outlined text-base text-[#1e8e3e]">groups</span>
            Registered Community Volunteers Nearby
          </span>
        </div>
        <div id="donorsList" class="space-y-2 mt-2"></div>
      </div>

      <!-- Professional WhatsApp & Social Dispatch Card -->
      <div class="m3-card p-5">
        <div class="flex justify-between items-center mb-3">
          <span class="text-xs font-bold uppercase tracking-wider text-[#1f1f1f] flex items-center gap-1.5">
            <i class="fa-brands fa-whatsapp text-emerald-600 text-base"></i> Emergency Broadcast Dispatch
          </span>
          <div class="bg-[#f1f3f4] p-0.5 rounded-full flex gap-1 text-xs font-medium">
            <button onclick="setLang('en')" id="btnEn" class="px-3 py-0.5 rounded-full bg-white text-[#1f1f1f] shadow-sm">English</button>
            <button onclick="setLang('kn')" id="btnKn" class="px-3 py-0.5 rounded-full text-[#444746]">ಕನ್ನಡ</button>
          </div>
        </div>

        <!-- WhatsApp Interactive Message Card -->
        <div class="bg-[#0b141a] p-3 rounded-2xl shadow-inner mb-3 overflow-hidden">
          <div class="bg-[#202c33] rounded-2xl shadow-md border border-[#2a3942] overflow-hidden">
            <div class="p-3.5 text-xs text-[#e9edef] whitespace-pre-wrap font-sans leading-relaxed" id="waMessageText"></div>
            
            <div class="px-3.5 pb-2 text-[10px] text-[#8696a0] flex justify-between items-center">
              <span>Click buttons below to navigate or accept</span>
              <span class="flex items-center">2:07 pm <i class="fa-solid fa-check-double text-[#53bdeb] ml-1 text-[9px]"></i></span>
            </div>

            <div class="border-t border-[#2a3942]">
              <a id="waBubbleMapBtn" href="#" target="_blank" class="w-full py-2.5 text-center text-[#00a884] hover:bg-[#182229] active:bg-[#111b21] font-semibold text-xs tracking-wide transition flex items-center justify-center">
                <i class="fa-solid fa-arrow-up-right-from-square mr-2 text-[11px]"></i> View Hospital Location
              </a>
            </div>

            <div class="border-t border-[#2a3942]">
              <a id="waBubbleAcceptBtn" href="#" target="_blank" class="w-full py-2.5 text-center text-[#00a884] hover:bg-[#182229] active:bg-[#111b21] font-semibold text-xs tracking-wide transition flex items-center justify-center">
                <i class="fa-solid fa-circle-check mr-2 text-[11px]"></i> Confirm & Donate (Accept)
              </a>
            </div>
          </div>
        </div>

        <div class="flex flex-col gap-2">
          <a id="waDirectBtn" href="#" target="_blank" class="w-full py-3 bg-[#25d366] hover:bg-[#1ebe5d] active:bg-[#128c7e] text-white font-medium text-sm rounded-full text-center shadow-sm transition flex items-center justify-center gap-2">
            <i class="fa-brands fa-whatsapp text-lg"></i>
            <span>Share SOS Broadcast on WhatsApp</span>
          </a>
          
          <div class="flex gap-2">
            <button onclick="copyMessage()" id="copyBtn" class="flex-1 py-2 rounded-full border border-[#74777f]/40 hover:bg-[#f8f9fa] text-xs font-medium text-[#1f1f1f] transition flex items-center justify-center gap-1.5">
              <span class="material-symbols-outlined text-base">content_copy</span>
              <span>Copy Text</span>
            </button>
            <a id="twDirectBtn" href="#" target="_blank" class="flex-1 py-2 rounded-full bg-[#0f1419] hover:bg-black text-white font-medium text-xs text-center transition flex items-center justify-center gap-1.5">
              <i class="fa-brands fa-x-twitter"></i>
              <span>Post on X</span>
            </a>
          </div>

          <button onclick="toggleApiPayload()" class="w-full py-2 rounded-full bg-[#f1f3f4] hover:bg-[#e8eaed] text-[#444746] font-medium text-xs transition flex items-center justify-center gap-1.5 mt-1">
            <span class="material-symbols-outlined text-base">code</span>
            <span>WhatsApp Cloud API Interactive Buttons Payload (JSON)</span>
          </button>
          <div id="apiPayloadBox" class="hidden bg-[#1f1f1f] text-[#a8dab5] p-3.5 rounded-2xl text-[11px] font-mono overflow-x-auto whitespace-pre border border-[#444746]"></div>
        </div>
      </div>

    </div>

    <!-- Live Emergency Requisitions Feed -->
    <div class="m3-card p-5">
      <div class="flex justify-between items-center mb-3">
        <div>
          <div class="flex items-center gap-2">
            <span class="w-2.5 h-2.5 rounded-full bg-[#d93025] animate-pulse"></span>
            <h2 class="text-sm font-bold text-[#1f1f1f]">Live Emergency Requests</h2>
            <span id="openCountBadge" class="text-[10px] font-bold bg-[#fce8e6] text-[#b3261e] px-2.5 py-0.5 rounded-full">Loading...</span>
          </div>
          <p class="text-[11px] text-[#444746] font-medium mt-0.5">Active hospital requisitions across Bengaluru. Tap below to accept and coordinate donation.</p>
        </div>
        <button onclick="loadEmergencies()" class="w-8 h-8 rounded-full hover:bg-[#f1f3f4] text-[#444746] flex items-center justify-center transition" title="Refresh Feed">
          <span class="material-symbols-outlined text-lg">refresh</span>
        </button>
      </div>

      <div id="emergenciesFeed" class="space-y-3">
        <div class="text-center py-4 text-xs text-[#444746]">
          <span class="material-symbols-outlined animate-spin text-xl text-[#0b57d0]">progress_activity</span>
          <p class="mt-1">Loading live emergency requisitions...</p>
        </div>
      </div>
    </div>

  </main>

  <!-- Sticky Bottom Bar for Mobile -->
  <div id="stickyMobileBar" class="hidden fixed bottom-3 left-4 right-4 max-w-lg mx-auto bg-white/95 backdrop-blur-md rounded-full border border-[#e0e2ec] p-2 shadow-xl z-40 flex items-center gap-2 md:hidden">
    <a id="stickyAcceptBtn" href="#" target="_blank" class="flex-1 py-2.5 bg-[#0b57d0] active:bg-[#0842a0] text-white font-medium text-xs rounded-full text-center shadow-sm flex items-center justify-center gap-1.5 whitespace-nowrap">
      <span class="material-symbols-outlined text-base">volunteer_activism</span>
      <span>I Can Donate</span>
    </a>
    <a id="stickyWaBtn" href="#" target="_blank" class="flex-1 py-2.5 bg-[#25d366] active:bg-[#128c7e] text-white font-medium text-xs rounded-full text-center shadow-sm flex items-center justify-center gap-1.5 whitespace-nowrap">
      <i class="fa-brands fa-whatsapp text-sm"></i>
      <span>Share SOS</span>
    </a>
    <a id="stickyCallBtn" href="#" class="w-10 h-10 bg-[#d93025] active:bg-[#b3261e] text-white rounded-full flex items-center justify-center shadow-sm shrink-0">
      <span class="material-symbols-outlined text-lg">call</span>
    </a>
  </div>

  <!-- Emergency Details Modal -->
  <div id="detailsModal" class="fixed inset-0 bg-[#000000]/50 backdrop-blur-sm z-50 flex items-center justify-center hidden p-4" onclick="if(event.target === this) closeDetailsModal()">
    <div class="m3-card max-w-lg w-full max-h-[90vh] overflow-y-auto p-5 md:p-6 shadow-2xl border-none">
      <!-- Header -->
      <div class="flex justify-between items-center pb-3 border-b border-[#e0e2ec]">
        <div class="flex items-center gap-2.5">
          <div class="w-9 h-9 rounded-full bg-[#e8f0fe] text-[#0b57d0] flex items-center justify-center shrink-0">
            <span class="material-symbols-outlined text-xl">medical_information</span>
          </div>
          <div>
            <h3 class="text-sm font-bold text-[#1f1f1f]">Emergency Requisition Details</h3>
            <p class="text-[11px] text-[#444746]" id="dtlCaseId">Case # --</p>
          </div>
        </div>
        <button onclick="closeDetailsModal()" class="w-8 h-8 rounded-full hover:bg-[#f1f3f4] text-[#444746] flex items-center justify-center text-lg">&times;</button>
      </div>

      <!-- Main Case Summary -->
      <div class="mt-4 p-4 rounded-2xl bg-[#f0f4f9] flex items-start gap-3.5">
        <div id="dtlBloodBadge" class="shrink-0">
          <!-- Blood group badge rendered here -->
        </div>
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-1.5 flex-wrap">
            <span class="text-sm font-bold text-[#1f1f1f]" id="dtlHospitalName">Hospital Name</span>
            <span class="text-[10px] font-bold px-2 py-0.5 rounded-full" id="dtlUrgencyBadge">URGENT</span>
            <span class="text-[10px] font-bold px-2 py-0.5 rounded-full" id="dtlStatusBadge">OPEN</span>
          </div>
          <p class="text-xs font-bold text-[#0b57d0] mt-1" id="dtlComponentUnits">Component • Units</p>
          <p class="text-[11px] text-[#444746] mt-0.5 flex items-center gap-1">
            <span class="material-symbols-outlined text-xs">patient_list</span>
            <span>Patient: <strong id="dtlPatientName" class="text-[#1f1f1f]">Name</strong></span>
          </p>
        </div>
      </div>

      <!-- Location & Hospital Card -->
      <div class="mt-3 p-3.5 rounded-2xl border border-[#e0e2ec] space-y-2 text-xs">
        <div class="font-bold text-[#1f1f1f] flex items-center gap-1.5">
          <span class="material-symbols-outlined text-sm text-[#0b57d0]">location_on</span>
          <span>Hospital & Transit Route</span>
        </div>
        <p class="text-[11px] text-[#444746] leading-relaxed pl-5" id="dtlAddress">Full Address</p>
        <p class="text-[11px] text-[#444746] pl-5 flex items-center gap-1">
          <span class="material-symbols-outlined text-xs">navigation</span>
          <span>Zone: <strong id="dtlZone">Bengaluru Zone</strong></span>
        </p>
        <div class="pt-1 pl-5">
          <a id="dtlMapLink" href="#" target="_blank" class="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full bg-white border border-[#74777f]/30 hover:bg-[#e8f0fe] text-[#0b57d0] text-[11px] font-medium shadow-xs transition">
            <span class="material-symbols-outlined text-sm">map</span>
            <span>View Route on Google Maps</span>
          </a>
        </div>
      </div>

      <!-- Attendant Contact Card -->
      <div class="mt-3 p-3.5 rounded-2xl border border-[#e0e2ec] space-y-2.5 text-xs">
        <div class="font-bold text-[#1f1f1f] flex items-center gap-1.5">
          <span class="material-symbols-outlined text-sm text-[#0b57d0]">contacts</span>
          <span>Emergency Coordinator / Attendant</span>
        </div>
        <div class="flex items-center justify-between pl-5 flex-wrap gap-2">
          <div>
            <div class="text-xs font-bold text-[#1f1f1f]" id="dtlAttendantName">Attendant Name</div>
            <div class="text-[11px] text-[#444746]" id="dtlAttendantPhone">+91 98860 12345</div>
          </div>
          <div class="flex items-center gap-1.5">
            <a id="dtlCallBtn" href="#" class="px-3.5 py-1.5 rounded-full bg-[#d93025] hover:bg-[#b3261e] text-white text-[11px] font-medium flex items-center gap-1 shadow-sm transition">
              <span class="material-symbols-outlined text-xs">call</span>
              <span>Call</span>
            </a>
            <a id="dtlWaBtn" href="#" target="_blank" class="px-3.5 py-1.5 rounded-full bg-[#25d366] hover:bg-[#128c7e] text-white text-[11px] font-medium flex items-center gap-1 shadow-sm transition">
              <i class="fa-brands fa-whatsapp text-xs"></i>
              <span>WhatsApp</span>
            </a>
          </div>
        </div>
      </div>

      <!-- Clinical Compatibility & Eligibility Criteria -->
      <div class="mt-3 p-3.5 rounded-2xl bg-[#fef7e0] border border-[#fde68a] text-xs">
        <div class="font-bold text-[#7c2d12] flex items-center gap-1.5 mb-1.5">
          <span class="material-symbols-outlined text-sm">clinical_notes</span>
          <span>Clinical Compatibility & Donor Eligibility</span>
        </div>
        <div class="text-[11px] text-[#7c2d12] space-y-1.5 pl-5">
          <div id="dtlCompatibleGroups" class="flex items-center gap-1.5 flex-wrap">
            <span class="font-bold">Compatible Donor Groups:</span>
          </div>
          <div>• Donors must be 18–65 yrs, &gt;50kg, no alcohol in past 24 hrs.</div>
          <div id="dtlSdpNotice">• For Platelets (SDP): Must NOT have taken Aspirin/NSAIDs in last 72 hours.</div>
        </div>
      </div>

      <!-- Modal Footer Action -->
      <div class="mt-4 pt-3 border-t border-[#e0e2ec]" id="dtlFooterAction">
        <!-- Rendered dynamically -->
      </div>
    </div>
  </div>

  <!-- Accept Modal -->
  <div id="acceptModal" class="fixed inset-0 bg-[#000000]/50 backdrop-blur-sm z-50 flex items-center justify-center hidden p-4">
    <div class="m3-card max-w-sm w-full p-6 shadow-2xl border-none">
      <div class="flex justify-between items-center mb-3 pb-2 border-b border-[#e0e2ec]">
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined text-[#0b57d0]">volunteer_activism</span>
          <h3 class="text-base font-bold text-[#1f1f1f]">Accept Blood Donation</h3>
        </div>
        <button onclick="closeAcceptModal()" class="w-8 h-8 rounded-full hover:bg-[#f1f3f4] text-[#444746] flex items-center justify-center text-lg">&times;</button>
      </div>

      <div class="bg-[#f0f4f9] rounded-2xl p-3 mb-3 text-xs">
        <div class="font-bold text-[#1f1f1f]" id="modalCaseTitle">Hospital Name</div>
        <div class="text-[#444746] mt-0.5" id="modalCaseSubtitle">Component • Units</div>
      </div>

      <div class="bg-[#fef7e0] border border-[#fde68a] rounded-xl p-2.5 mb-3 text-[11px] text-[#7c2d12] font-medium leading-snug">
        <div class="font-bold mb-0.5 flex items-center gap-1">
          <span class="material-symbols-outlined text-xs">verified</span> NBTC Donor Criteria:
        </div>
        <div>• Age 18–65, weight &gt;50kg, no alcohol in 24h</div>
        <div id="modalSdpCriteria">• Platelet (SDP): No Aspirin/painkillers in last 72h</div>
      </div>

      <form onsubmit="handleAcceptSubmit(event)" class="space-y-3 text-xs">
        <input type="hidden" id="acceptReqId">
        <input type="hidden" id="acceptAttendantPhone">
        <input type="hidden" id="acceptAttendantName">
        <input type="hidden" id="acceptHospName">
        <input type="hidden" id="acceptBloodGroup">

        <div>
          <label class="block font-medium text-[#444746] mb-1">Your Name</label>
          <input type="text" id="acceptDonorName" required class="w-full bg-white border border-[#74777f]/40 rounded-xl p-2.5 text-xs font-medium text-[#1f1f1f] focus:outline-none focus:border-[#0b57d0]" placeholder="e.g. Ramesh Kumar">
        </div>
        <div>
          <label class="block font-medium text-[#444746] mb-1">Your Phone Number (10 Digits)</label>
          <input type="tel" id="acceptDonorPhone" required class="w-full bg-white border border-[#74777f]/40 rounded-xl p-2.5 text-xs font-medium text-[#1f1f1f] focus:outline-none focus:border-[#0b57d0]" placeholder="+91 98860 12345">
        </div>

        <div class="pt-2 flex gap-2">
          <button type="button" onclick="closeAcceptModal()" class="flex-1 py-2.5 rounded-full border border-[#74777f]/40 text-[#444746] font-medium text-xs hover:bg-[#f1f3f4]">Cancel</button>
          <button type="submit" id="confirmAcceptBtn" class="flex-1 py-2.5 rounded-full bg-[#0b57d0] text-white font-medium text-xs hover:bg-[#0842a0] flex items-center justify-center gap-1 shadow-sm">
            <span class="material-symbols-outlined text-sm">check_circle</span>
            <span>Confirm & WhatsApp</span>
          </button>
        </div>
      </form>
    </div>
  </div>

  <!-- Register Donor Modal -->
  <div id="donorModal" class="fixed inset-0 bg-[#000000]/50 backdrop-blur-sm z-50 flex items-center justify-center hidden p-4">
    <div class="m3-card max-w-sm w-full p-6 shadow-2xl border-none">
      <div class="flex justify-between items-center mb-4 pb-2 border-b border-[#e0e2ec]">
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined text-[#0b57d0]">person_add</span>
          <h3 class="text-base font-bold text-[#1f1f1f]">Register Volunteer Donor</h3>
        </div>
        <button onclick="closeDonorModal()" class="w-8 h-8 rounded-full hover:bg-[#f1f3f4] text-[#444746] flex items-center justify-center text-lg">&times;</button>
      </div>
      <form onsubmit="handleDonorSubmit(event)" class="space-y-3.5 text-xs">
        <div>
          <label class="block font-medium text-[#444746] mb-1">Full Name</label>
          <input type="text" id="regName" required class="w-full bg-white border border-[#74777f]/40 rounded-xl p-2.5 text-xs font-medium text-[#1f1f1f] focus:outline-none focus:border-[#0b57d0]" placeholder="e.g. Ramesh Kumar">
        </div>
        <div>
          <label class="block font-medium text-[#444746] mb-1">Phone Number (10 Digits)</label>
          <input type="tel" id="regPhone" required class="w-full bg-white border border-[#74777f]/40 rounded-xl p-2.5 text-xs font-medium text-[#1f1f1f] focus:outline-none focus:border-[#0b57d0]" placeholder="+91 98860 12345">
        </div>
        <div class="grid grid-cols-2 gap-2">
          <div>
            <label class="block font-medium text-[#444746] mb-1">Blood Group</label>
            <select id="regGroup" class="w-full bg-white border border-[#74777f]/40 rounded-xl p-2.5 text-xs font-bold text-[#1f1f1f] focus:outline-none focus:border-[#0b57d0]">
              <option value="A+">A+</option>
              <option value="A-">A-</option>
              <option value="B+">B+</option>
              <option value="B-">B-</option>
              <option value="O+">O+</option>
              <option value="O-">O-</option>
              <option value="AB+">AB+</option>
              <option value="AB-">AB-</option>
              <option value="Bombay (hh)">Bombay (hh)</option>
            </select>
          </div>
          <div>
            <label class="block font-medium text-[#444746] mb-1">Zone</label>
            <select id="regZone" class="w-full bg-white border border-[#74777f]/40 rounded-xl p-2.5 text-xs font-medium text-[#1f1f1f] focus:outline-none focus:border-[#0b57d0]">
              <option value="East Bengaluru (Indiranagar, Whitefield, Marathahalli, HAL)">East (Indiranagar)</option>
              <option value="South Bengaluru (Jayanagar, BTM, HSR, Koramangala, Bannerghatta, E-City)">South (Jayanagar)</option>
              <option value="Central Bengaluru (Majestic, MG Road, Shivaji Nagar, Market)">Central (Majestic)</option>
              <option value="North Bengaluru (Hebbal, Yelahanka, Manyata, Mathikere)">North (Hebbal)</option>
              <option value="West Bengaluru (Malleshwaram, Rajajinagar, Vijayanagar, Kengeri)">West (Malleshwaram)</option>
            </select>
          </div>
        </div>
        <div>
          <label class="block font-medium text-[#444746] mb-1">Area / Landmark</label>
          <input type="text" id="regArea" required class="w-full bg-white border border-[#74777f]/40 rounded-xl p-2.5 text-xs font-medium text-[#1f1f1f] focus:outline-none focus:border-[#0b57d0]" placeholder="e.g. HSR Layout Sector 2">
        </div>
        <div class="flex items-center pt-1">
          <input type="checkbox" id="regSDP" class="w-4 h-4 text-[#0b57d0] rounded mr-2 focus:ring-0">
          <label for="regSDP" class="text-xs font-medium text-[#1f1f1f]">Willing to donate Platelets (SDP apheresis)?</label>
        </div>
        <div class="pt-3 flex gap-2">
          <button type="button" onclick="closeDonorModal()" class="flex-1 py-2.5 rounded-full border border-[#74777f]/40 text-[#444746] font-medium text-xs hover:bg-[#f1f3f4]">Cancel</button>
          <button type="submit" id="saveDonorBtn" class="flex-1 py-2.5 rounded-full bg-[#0b57d0] text-white font-medium text-xs hover:bg-[#0842a0]">Save Donor</button>
        </div>
      </form>
    </div>
  </div>

  <script>
    const cases = {
      manipal: "Urgent: Need 2 units of A+ platelets (SDP) for dengue patient with critical platelet drop at Manipal Hospital, HAL Old Airport Road. Attendant Suresh: 9886012345. IP: 5542.",
      victoria: "Emergency: Need 3 units of O-negative whole blood immediately for road accident trauma at Victoria Hospital, KR Market. Contact Dr. Ramesh: 9845011223.",
      kidwai: "Required 1 unit Single Donor Platelet B+ for leukemia patient at Kidwai Memorial Institute of Oncology, Hosur Road. Attendant Anitha: 9900112233.",
      jayadeva: "CRITICAL: Bombay blood group patient in ICU at Jayadeva Institute of Cardiovascular Sciences, Bannerghatta Road. Needs 2 units packed red cells immediately. Contact: 9741098765."
    };

    let activeData = null;
    let selectedLang = 'en';
    let currentEmergencies = [];

    function handleCaseSelect(val) {
      if (val && cases[val]) {
        document.getElementById('rawInput').value = cases[val];
        runTriage();
      }
    }

    function openDonorModal() {
      document.getElementById('donorModal').classList.remove('hidden');
    }

    function closeDonorModal() {
      document.getElementById('donorModal').classList.add('hidden');
    }

    async function handleDonorSubmit(e) {
      e.preventDefault();
      const payload = {
        name: document.getElementById('regName').value.trim(),
        phone: document.getElementById('regPhone').value.trim(),
        blood_group: document.getElementById('regGroup').value,
        zone: document.getElementById('regZone').value,
        area: document.getElementById('regArea').value.trim(),
        can_donate_sdp: document.getElementById('regSDP').checked
      };

      const btn = document.getElementById('saveDonorBtn');
      btn.textContent = 'Saving...';
      btn.disabled = true;

      try {
        await fetch('/api/register_donor', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(payload)
        });
        alert("Thank you! You have been registered as a voluntary donor.");
        closeDonorModal();
      } catch (err) {
        alert("Error saving: " + err);
      } finally {
        btn.textContent = 'Save Donor';
        btn.disabled = false;
      }
    }

    async function loadEmergencies() {
      try {
        const res = await fetch('/api/emergencies');
        const data = await res.json();
        currentEmergencies = data;
        renderEmergencies(data);
      } catch (err) {
        console.error("Error loading emergencies:", err);
      }
    }

    function renderBloodGroupBadge(bg, isOpen) {
      const isBombay = bg && bg.toLowerCase().includes('bombay');
      const bgClass = isOpen ? 'bg-[#fce8e6] text-[#b3261e]' : 'bg-[#e6f4ea] text-[#137333]';
      if (isBombay) {
        return `
          <div class="min-w-[48px] h-10 px-1 rounded-2xl ${bgClass} font-bold flex flex-col items-center justify-center shrink-0 leading-tight border border-[#f5c2c7]">
            <span class="text-[8px] uppercase tracking-tighter opacity-80 font-bold">Bombay</span>
            <span class="text-[11px] font-black -mt-0.5">(hh)</span>
          </div>
        `;
      }
      return `
        <div class="w-10 h-10 rounded-2xl ${bgClass} font-bold text-xs flex items-center justify-center shrink-0">
          ${bg}
        </div>
      `;
    }

    function renderEmergencies(list) {
      const container = document.getElementById('emergenciesFeed');
      const countBadge = document.getElementById('openCountBadge');
      if (!container) return;

      const openCount = list.filter(e => e.status === 'OPEN').length;
      if (countBadge) {
        countBadge.textContent = `${openCount} Open`;
      }

      if (!list || list.length === 0) {
        container.innerHTML = '<p class="text-xs text-[#444746] italic p-2">No active emergency requests right now.</p>';
        return;
      }

      container.innerHTML = list.map(item => {
        const isOpen = (item.status === 'OPEN');
        const isCritical = item.urgency && item.urgency.includes('CRITICAL');
        
        const cleanPhone = (item.contact_phone || '').replace(/[^0-9]/g, '');
        const phoneWithCode = cleanPhone.length === 10 ? '91' + cleanPhone : cleanPhone;
        const waLink = `https://wa.me/${phoneWithCode}?text=Hi+${encodeURIComponent(item.contact_name || 'Attendant')},+I+can+donate+${encodeURIComponent(item.blood_group)}+for+patient+at+${encodeURIComponent(item.hospital_name)}`;

        const safeHosp = (item.hospital_name || '').replace(/'/g, "\\'");
        const safeContact = (item.contact_name || 'Attendant').replace(/'/g, "\\'");

        return `
          <div onclick="openEmergencyDetailsModal(${item.id})" class="p-3.5 rounded-2xl border ${isOpen ? 'border-[#e0e2ec] bg-white hover:border-[#0b57d0]/60 hover:shadow-md' : 'border-emerald-200 bg-emerald-50/50 hover:border-emerald-300 hover:shadow-sm'} transition cursor-pointer group">
            <div class="flex justify-between items-start gap-2 mb-2">
              <div class="flex items-center gap-2.5 min-w-0">
                ${renderBloodGroupBadge(item.blood_group, isOpen)}
                <div class="min-w-0">
                  <div class="flex items-center gap-1.5 flex-wrap">
                    <span class="font-bold text-xs text-[#1f1f1f] group-hover:text-[#0b57d0] transition">${item.hospital_name}</span>
                    <span class="text-[10px] font-bold px-2 py-0.5 rounded-full ${isCritical ? 'bg-[#f9dedc] text-[#410002]' : 'bg-[#e8f0fe] text-[#0b57d0]'}">
                      ${item.urgency ? item.urgency.split('(')[0].trim() : 'URGENT'}
                    </span>
                    <span class="text-[10px] font-bold px-2 py-0.5 rounded-full ${isOpen ? 'bg-[#e6f4ea] text-[#137333]' : 'bg-slate-200 text-slate-700'}">
                      ${item.status}
                    </span>
                  </div>
                  <p class="text-[11px] text-[#444746] font-medium mt-0.5 truncate">
                    ${item.component} • ${item.units} Unit(s) • ${item.hospital_address || (item.zone ? item.zone.split('(')[0].trim() : 'Bengaluru')}
                  </p>
                </div>
              </div>
              <div class="flex items-center text-[#74777f] group-hover:text-[#0b57d0] shrink-0 transition pt-1">
                <span class="material-symbols-outlined text-base">chevron_right</span>
              </div>
            </div>

            <div class="flex items-center justify-between pt-2 border-t border-[#f1f3f4] text-xs gap-2">
              <div class="text-[11px] text-[#444746] flex items-center gap-1 min-w-0 truncate">
                <span class="material-symbols-outlined text-sm shrink-0">person</span>
                <span class="truncate">Attendant: <strong>${item.contact_name}</strong> (${item.contact_phone})</span>
              </div>

              ${isOpen ? `
                <button onclick="event.stopPropagation(); openAcceptModal(${item.id}, '${item.blood_group}', '${item.component}', '${safeHosp}', '${safeContact}', '${phoneWithCode}')" class="rounded-full bg-[#0b57d0] hover:bg-[#0842a0] text-white font-medium text-xs px-3.5 py-1.5 shadow-sm flex items-center gap-1 transition shrink-0 whitespace-nowrap">
                  <span class="material-symbols-outlined text-sm">volunteer_activism</span>
                  <span>I Can Donate</span>
                </button>
              ` : `
                <div class="flex items-center gap-1.5 shrink-0 whitespace-nowrap" onclick="event.stopPropagation()">
                  <span class="text-[11px] font-bold text-[#137333] bg-[#e6f4ea] px-2.5 py-0.5 rounded-full flex items-center gap-1">
                    <span class="material-symbols-outlined text-xs">check_circle</span>
                    <span>Accepted by ${item.accepted_by || 'Volunteer'}</span>
                  </span>
                  <a href="${waLink}" target="_blank" onclick="event.stopPropagation()" class="rounded-full border border-[#74777f]/40 hover:bg-[#f1f3f4] text-[#137333] font-medium text-xs px-2.5 py-0.5 flex items-center gap-1">
                    <i class="fa-brands fa-whatsapp"></i> Chat
                  </a>
                </div>
              `}
            </div>
          </div>
        `;
      }).join('');
    }

    function getCompatibleGroups(bg, comp) {
      if (!bg) return ['Any'];
      const isBombay = bg.toLowerCase().includes('bombay');
      if (isBombay) return ['Bombay (hh)'];
      const isPlatelet = comp && (comp.toLowerCase().includes('platelet') || comp.toLowerCase().includes('sdp'));
      if (isPlatelet) {
        const pMap = {
          'O+': ['O+', 'O-', 'A+', 'B+'],
          'O-': ['O-', 'O+'],
          'A+': ['A+', 'A-', 'AB+'],
          'A-': ['A-', 'A+'],
          'B+': ['B+', 'B-', 'AB+'],
          'B-': ['B-', 'B+'],
          'AB+': ['AB+', 'AB-', 'A+', 'B+'],
          'AB-': ['AB-', 'AB+']
        };
        return pMap[bg] || [bg];
      } else {
        const rbcMap = {
          'O-': ['O-'],
          'O+': ['O+', 'O-'],
          'A-': ['A-', 'O-'],
          'A+': ['A+', 'A-', 'O+', 'O-'],
          'B-': ['B-', 'O-'],
          'B+': ['B+', 'B-', 'O+', 'O-'],
          'AB-': ['AB-', 'A-', 'B-', 'O-'],
          'AB+': ['AB+', 'AB-', 'A+', 'A-', 'B+', 'B-', 'O+', 'O-']
        };
        return rbcMap[bg] || [bg];
      }
    }

    function openEmergencyDetailsModal(id) {
      const item = currentEmergencies.find(e => e.id === id);
      if (!item) return;

      const isOpen = (item.status === 'OPEN');
      const isCritical = item.urgency && item.urgency.includes('CRITICAL');
      const isPlatelet = item.component && (item.component.toLowerCase().includes('platelet') || item.component.toLowerCase().includes('sdp'));

      const cleanPhone = (item.contact_phone || '').replace(/[^0-9]/g, '');
      const phoneWithCode = cleanPhone.length === 10 ? '91' + cleanPhone : cleanPhone;
      const waLink = `https://wa.me/${phoneWithCode}?text=Hi+${encodeURIComponent(item.contact_name || 'Attendant')},+I+can+donate+${encodeURIComponent(item.blood_group)}+for+patient+at+${encodeURIComponent(item.hospital_name)}`;
      const mapsLink = `https://maps.google.com/?q=${encodeURIComponent(item.hospital_name + ' ' + (item.hospital_address || 'Bengaluru'))}`;

      // Case ID & Header
      document.getElementById('dtlCaseId').textContent = `Req #${item.id} • Registered ${item.created_at || 'Recently'}`;
      document.getElementById('dtlBloodBadge').innerHTML = renderBloodGroupBadge(item.blood_group, isOpen);
      document.getElementById('dtlHospitalName').textContent = item.hospital_name;
      
      const urgEl = document.getElementById('dtlUrgencyBadge');
      urgEl.textContent = item.urgency ? item.urgency.split('(')[0].trim() : 'URGENT';
      urgEl.className = `text-[10px] font-bold px-2 py-0.5 rounded-full ${isCritical ? 'bg-[#f9dedc] text-[#410002]' : 'bg-[#e8f0fe] text-[#0b57d0]'}`;

      const statEl = document.getElementById('dtlStatusBadge');
      statEl.textContent = item.status;
      statEl.className = `text-[10px] font-bold px-2 py-0.5 rounded-full ${isOpen ? 'bg-[#e6f4ea] text-[#137333]' : 'bg-slate-200 text-slate-700'}`;

      document.getElementById('dtlComponentUnits').textContent = `${item.component} • ${item.units} Unit(s) Required`;
      document.getElementById('dtlPatientName').textContent = item.patient_name || 'Emergency Patient';

      // Location
      document.getElementById('dtlAddress').textContent = item.hospital_address || 'Address provided on clinical coordination';
      document.getElementById('dtlZone').textContent = item.zone || 'Bengaluru';
      document.getElementById('dtlMapLink').href = mapsLink;

      // Contact
      document.getElementById('dtlAttendantName').textContent = item.contact_name || 'Attendant';
      document.getElementById('dtlAttendantPhone').textContent = item.contact_phone || 'Not available';
      document.getElementById('dtlCallBtn').href = cleanPhone ? `tel:${cleanPhone}` : '#';
      document.getElementById('dtlWaBtn').href = waLink;

      // Compatibility chips
      const compatibleGroups = getCompatibleGroups(item.blood_group, item.component);
      const compContainer = document.getElementById('dtlCompatibleGroups');
      compContainer.innerHTML = `<span class="font-bold">Compatible Donor Groups:</span> ` + 
        compatibleGroups.map(bg => `<span class="bg-[#fde68a] text-[#7c2d12] px-2 py-0.5 rounded-md font-bold text-[10px]">${bg}</span>`).join(' ');

      // Platelet criteria notice
      const sdpNotice = document.getElementById('dtlSdpNotice');
      if (sdpNotice) {
        sdpNotice.style.display = isPlatelet ? 'block' : 'none';
      }

      // Footer
      const footerEl = document.getElementById('dtlFooterAction');
      const safeHosp = (item.hospital_name || '').replace(/'/g, "\\'");
      const safeContact = (item.contact_name || 'Attendant').replace(/'/g, "\\'");

      if (isOpen) {
        footerEl.innerHTML = `
          <button onclick="closeDetailsModal(); openAcceptModal(${item.id}, '${item.blood_group}', '${item.component}', '${safeHosp}', '${safeContact}', '${phoneWithCode}')" class="w-full py-2.5 rounded-full bg-[#0b57d0] hover:bg-[#0842a0] text-white font-medium text-xs flex items-center justify-center gap-1.5 shadow-sm transition">
            <span class="material-symbols-outlined text-sm">volunteer_activism</span>
            <span>I Can Donate (Accept & Connect via WhatsApp)</span>
          </button>
        `;
      } else {
        footerEl.innerHTML = `
          <div class="bg-[#e6f4ea] text-[#137333] p-3 rounded-2xl text-xs font-medium flex items-center justify-between">
            <span class="flex items-center gap-1.5">
              <span class="material-symbols-outlined text-base">check_circle</span>
              <span>Accepted by <strong>${item.accepted_by || 'Volunteer'}</strong></span>
            </span>
            <a href="${waLink}" target="_blank" class="px-3 py-1 rounded-full bg-[#137333] text-white text-[11px] font-medium flex items-center gap-1">
              <i class="fa-brands fa-whatsapp"></i> Chat
            </a>
          </div>
        `;
      }

      document.getElementById('detailsModal').classList.remove('hidden');
    }

    function closeDetailsModal() {
      document.getElementById('detailsModal').classList.add('hidden');
    }

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeDetailsModal();
        closeAcceptModal();
        closeDonorModal();
      }
    });

    function openAcceptModal(reqId, bloodGroup, component, hospName, contactName, phone) {
      document.getElementById('acceptReqId').value = reqId;
      document.getElementById('acceptBloodGroup').value = bloodGroup;
      document.getElementById('acceptHospName').value = hospName;
      document.getElementById('acceptAttendantName').value = contactName;
      document.getElementById('acceptAttendantPhone').value = phone;

      document.getElementById('modalCaseTitle').textContent = `${hospName} • ${bloodGroup}`;
      document.getElementById('modalCaseSubtitle').textContent = `${component} • Attendant: ${contactName}`;
      
      const sdpBox = document.getElementById('modalSdpCriteria');
      if (component.includes('Platelet') || component.includes('SDP')) {
        sdpBox.style.display = 'block';
      } else {
        sdpBox.style.display = 'none';
      }

      document.getElementById('acceptModal').classList.remove('hidden');
    }

    function closeAcceptModal() {
      document.getElementById('acceptModal').classList.add('hidden');
    }

    async function handleAcceptSubmit(e) {
      e.preventDefault();
      const reqId = document.getElementById('acceptReqId').value;
      const donorName = document.getElementById('acceptDonorName').value.trim();
      const donorPhone = document.getElementById('acceptDonorPhone').value.trim();
      const attendantPhone = document.getElementById('acceptAttendantPhone').value;
      const attendantName = document.getElementById('acceptAttendantName').value;
      const hosp = document.getElementById('acceptHospName').value;
      const bg = document.getElementById('acceptBloodGroup').value;

      const btn = document.getElementById('confirmAcceptBtn');
      btn.textContent = 'Accepting...';
      btn.disabled = true;

      try {
        const res = await fetch('/api/accept_emergency', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            request_id: reqId,
            donor_name: donorName,
            donor_phone: donorPhone
          })
        });
        const result = await res.json();
        if (result.success) {
          closeAcceptModal();
          if (typeof loadEmergencies === 'function') {
            await loadEmergencies();
          }
          
          const text = encodeURIComponent(`Hi ${attendantName}, I have accepted to donate ${bg} blood for the patient at ${hosp}. My name is ${donorName} (${donorPhone}). I am ready to coordinate.`);
          window.open(`https://wa.me/${attendantPhone}?text=${text}`, '_blank');
        } else {
          alert("Error accepting request: " + (result.error || "Unknown error"));
        }
      } catch (err) {
        alert("Network error: " + err);
      } finally {
        btn.innerHTML = '<span class="material-symbols-outlined text-sm">check_circle</span><span>Confirm & WhatsApp</span>';
        btn.disabled = false;
      }
    }

    async function runTriage() {
      const text = document.getElementById('rawInput').value.trim();
      if (!text) {
        alert("Please describe the emergency or pick a sample case.");
        return;
      }

      const btn = document.getElementById('triageBtn');
      btn.innerHTML = '<span class="material-symbols-outlined animate-spin text-xl">progress_activity</span><span>Analyzing Requisition...</span>';
      btn.disabled = true;

      try {
        const response = await fetch('/api/triage', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: text })
        });
        const data = await response.json();
        renderResults(data);
        if (typeof loadEmergencies === 'function') {
          loadEmergencies();
        }
      } catch (err) {
        alert("Error running triage: " + err);
      } finally {
        btn.innerHTML = '<span class="material-symbols-outlined text-xl">search</span><span>Find Compatible Donors & Blood Banks</span>';
        btn.disabled = false;
      }
    }

    function renderResults(data) {
      activeData = data;

      if (data.is_guardrail_blocked) {
        document.getElementById('resultsWrapper').classList.add('hidden');
        document.getElementById('validationBanner').classList.add('hidden');
        document.getElementById('stickyMobileBar').classList.add('hidden');
        document.getElementById('guardrailAlert').classList.remove('hidden');
        document.getElementById('guardrailText').textContent = data.guardrail_message || data.actionable_advice;
        document.getElementById('guardrailAlert').scrollIntoView({ behavior: 'smooth' });
        return;
      }

      document.getElementById('guardrailAlert').classList.add('hidden');
      document.getElementById('resultsWrapper').classList.remove('hidden');
      document.getElementById('stickyMobileBar').classList.remove('hidden');

      const valBanner = document.getElementById('validationBanner');
      const warningsList = document.getElementById('warningsList');
      if (data.validation_warnings && data.validation_warnings.length > 0) {
        valBanner.classList.remove('hidden');
        warningsList.innerHTML = data.validation_warnings.map(w => `
          <li>• [${w.field}]: ${w.message}</li>
        `).join('');
      } else {
        valBanner.classList.add('hidden');
      }

      const req = data.requirement;
      const comp = data.compatibility;
      document.getElementById('urgencyBadge').textContent = req.urgency ? req.urgency.split('(')[0].trim() : 'URGENT';
      document.getElementById('caseTitle').textContent = `${req.blood_group} ${req.component} • ${req.units} Unit(s)`;
      document.getElementById('caseLocation').innerHTML = `<span class="material-symbols-outlined text-[#d93025] text-base material-symbols-fill mr-1">location_on</span> ${req.hospital_name}`;
      document.getElementById('caseContact').textContent = `${req.contact_name} (${req.contact_phone})`;

      document.getElementById('donorPills').innerHTML = comp.compatible_donor_groups.map(g => {
        const isMatch = (g === comp.ideal_donor_group);
        return `<span class="px-3.5 py-1.5 rounded-full text-xs font-bold ${isMatch ? 'bg-[#d93025] text-white shadow-sm' : 'bg-[#e8f0fe] text-[#0b57d0] border border-[#d3e3fd]'}">${g}${isMatch ? ' (Exact Match)' : ''}</span>`;
      }).join('');

      const note = comp.clinical_notes.join(' • ');
      const sdpRule = req.component.includes("Platelets") ? " • ⚠️ Donor must not have taken Aspirin/NSAIDs in last 72 hours." : "";
      document.getElementById('clinicalRuleBox').innerHTML = `<span class="material-symbols-outlined text-sm text-[#0b57d0] shrink-0 mt-0.5">info</span><span>${note + sdpRule}</span>`;

      if (data.matched_blood_banks && data.matched_blood_banks.length > 0) {
        const topBank = data.matched_blood_banks[0];
        document.getElementById('topBankName').textContent = topBank.name;
        document.getElementById('topBankArea').innerHTML = `<span class="material-symbols-outlined text-sm text-[#1e8e3e]">directions_subway</span><span>${topBank.area} • Metro: ${topBank.metro_proximity}</span>`;
        document.getElementById('topBankTransit').innerHTML = `<span class="material-symbols-outlined text-sm text-[#ea8600] shrink-0 mt-0.5">warning</span><span>${topBank.peak_traffic_advisory}</span>`;
        document.getElementById('topBankCall').href = `tel:${topBank.phone.split('/')[0].trim()}`;
        document.getElementById('topBankMap').href = `https://www.google.com/maps/search/?api=1&query=${topBank.google_maps_query}`;
        document.getElementById('stickyCallBtn').href = `tel:${topBank.phone.split('/')[0].trim()}`;
      }

      const donors = data.matched_donors;
      const donorsDiv = document.getElementById('donorsList');
      if (donors && donors.length > 0) {
        donorsDiv.innerHTML = donors.map(d => `
          <div class="p-3 rounded-2xl border border-[#e0e2ec] bg-white flex justify-between items-center text-xs hover:bg-[#f8fafd] transition">
            <div class="flex items-center gap-3">
              ${renderBloodGroupBadge(d.blood_group, true)}
              <div>
                <div class="flex items-center space-x-1.5">
                  <span class="font-bold text-xs text-[#1f1f1f]">${d.name}</span>
                  ${d.can_donate_sdp ? '<span class="text-[10px] bg-[#e6f4ea] text-[#137333] font-medium px-2 py-0.5 rounded-full">Platelets Ready</span>' : ''}
                </div>
                <p class="text-[#444746] text-[11px] mt-0.5">${d.area} (${d.zone ? d.zone.split('(')[0].trim() : 'Bengaluru'})</p>
              </div>
            </div>
            <a href="tel:${d.phone}" class="px-3.5 py-1.5 rounded-full border border-[#74777f]/40 hover:bg-[#f1f3f4] text-[#0b57d0] font-medium text-xs shrink-0 flex items-center gap-1">
              <span class="material-symbols-outlined text-sm">call</span> Call
            </a>
          </div>
        `).join('');
      } else {
        donorsDiv.innerHTML = '<p class="text-xs text-[#444746] italic p-1">No individual registered donors in this zone right now. Please call verified 24/7 blood banks above.</p>';
      }

      updateBroadcastPreview();
      document.getElementById('waBubbleMapBtn').href = data.sos.hospital_maps_url || '#';
      document.getElementById('waBubbleAcceptBtn').href = data.sos.donor_accept_url || '#';
      document.getElementById('stickyAcceptBtn').href = data.sos.donor_accept_url || '#';
      document.getElementById('waDirectBtn').href = data.sos.whatsapp_share_url;
      document.getElementById('stickyWaBtn').href = data.sos.whatsapp_share_url;
      document.getElementById('twDirectBtn').href = data.sos.twitter_share_url;

      // No disruptive auto-scroll
    }

    function setLang(lang) {
      selectedLang = lang;
      if (lang === 'en') {
        document.getElementById('btnEn').className = "px-3 py-0.5 rounded-full bg-white text-[#1f1f1f] shadow-sm";
        document.getElementById('btnKn').className = "px-3 py-0.5 rounded-full text-[#444746]";
      } else {
        document.getElementById('btnEn').className = "px-3 py-0.5 rounded-full text-[#444746]";
        document.getElementById('btnKn').className = "px-3 py-0.5 rounded-full bg-white text-[#1f1f1f] shadow-sm";
      }
      updateBroadcastPreview();
    }

    function updateBroadcastPreview() {
      if (!activeData || !activeData.requirement) return;
      const req = activeData.requirement;
      const comp = activeData.compatibility;
      const compGroups = (comp && comp.compatible_donor_groups) ? comp.compatible_donor_groups.join(', ') : 'All compatible';
      
      let previewBody = '';
      if (selectedLang === 'en') {
        previewBody = `🚨 *URGENT BLOOD REQUIREMENT - BENGALURU*\n\n` +
          `• *Hospital:* ${req.hospital_name}\n` +
          `• *Location:* ${req.hospital_address || (req.zone ? req.zone.split('(')[0].trim() : 'Bengaluru')}\n` +
          `• *Blood Group:* *${req.blood_group}*\n` +
          `• *Component:* ${req.component}\n` +
          `• *Units Required:* ${req.units}\n` +
          `• *Compatible Donors:* ${compGroups}\n` +
          `• *Patient:* ${req.patient_name || 'Emergency Patient'}` + (req.case_or_ip_number ? ` (IP: ${req.case_or_ip_number})` : '') + `\n` +
          `• *Contact Attendant:* *${req.contact_name}* - *${req.contact_phone}*\n\n` +
          `Click below to navigate or accept`;
      } else {
        previewBody = `🚨 *ತುರ್ತು ರಕ್ತದ ಅವಶ್ಯಕತೆ - ಬೆಂಗಳೂರು*\n\n` +
          `• ಆಸ್ಪತ್ರೆ: ${req.hospital_name}\n` +
          `• ಸ್ಥಳ: ${req.hospital_address || (req.zone ? req.zone.split('(')[0].trim() : 'ಬೆಂಗಳೂರು')}\n` +
          `• ರಕ್ತದ ಗುಂಪು: *${req.blood_group}* (${req.component})\n` +
          `• ಘಟಕಗಳು: ${req.units}\n` +
          `• ಹೊಂದಾಣಿಕೆ: ${compGroups}\n` +
          `• ಸಂಪರ್ಕ: *${req.contact_name}* - *${req.contact_phone}*\n\n` +
          `ಸ್ಥಳ ನೋಡಲು ಅಥವಾ ದಾನ ಮಾಡಲು ಕೆಳಗಿನ ಬಟನ್ ಒತ್ತಿರಿ`;
      }
      document.getElementById('waMessageText').textContent = previewBody;
    }

    function toggleApiPayload() {
      const box = document.getElementById('apiPayloadBox');
      if (!activeData || !activeData.sos) return;
      if (box.classList.contains('hidden')) {
        box.classList.remove('hidden');
        box.textContent = JSON.stringify(activeData.sos.whatsapp_cloud_api_payload, null, 2);
      } else {
        box.classList.add('hidden');
      }
    }

    function copyMessage() {
      if (!activeData) return;
      const text = (selectedLang === 'en') ? activeData.sos.english_text : activeData.sos.kannada_text;
      navigator.clipboard.writeText(text).then(() => {
        const btn = document.getElementById('copyBtn');
        btn.innerHTML = '<span class="material-symbols-outlined text-base text-[#137333]">check</span><span>Copied!</span>';
        setTimeout(() => {
          btn.innerHTML = '<span class="material-symbols-outlined text-base">content_copy</span><span>Copy Text</span>';
        }, 2000);
      });
    }

    // Call immediately on load
    if (typeof loadEmergencies === 'function') {
      loadEmergencies();
    }
  </script>
</body>
</html>"""


class NammaRakthaHandler(BaseHTTPRequestHandler):
    """
    HTTP Request Handler serving mobile-first web UI and triage API.
    """

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
        elif self.path == "/api/bloodbanks":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            banks_data = [b.model_dump() for b in BENGALURU_BLOOD_BANKS]
            self.wfile.write(json.dumps(banks_data).encode("utf-8"))
        elif self.path == "/api/donors_count":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            count = get_all_donors_count()
            self.wfile.write(json.dumps({"count": count}).encode("utf-8"))
        elif self.path == "/api/emergencies":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            emergencies = get_recent_emergencies(limit=10)
            self.wfile.write(json.dumps(emergencies).encode("utf-8"))
        elif self.path in ["/favicon.ico", "/favicon.svg"]:
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(FAVICON_SVG.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def do_POST(self):
        if self.path == "/api/triage":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode("utf-8"))
                input_text = payload.get("text", "")
                result = agent.triage(input_text)
                response_json = result.model_dump()

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(response_json).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
        elif self.path == "/api/register_donor":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode("utf-8"))
                donor_id = add_donor(
                    name=payload.get("name", "Volunteer"),
                    phone=payload.get("phone", ""),
                    blood_group=payload.get("blood_group", "O+"),
                    zone=payload.get("zone", "Central Bengaluru (Majestic, MG Road, Shivaji Nagar, Market)"),
                    area=payload.get("area", "Bengaluru"),
                    can_donate_sdp=bool(payload.get("can_donate_sdp", False))
                )
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "donor_id": donor_id}).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
        elif self.path == "/api/accept_emergency":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode("utf-8"))
                req_id = int(payload.get("request_id", 0))
                donor_name = payload.get("donor_name", "Volunteer Donor")
                donor_phone = payload.get("donor_phone", "")
                success = accept_emergency(req_id, donor_name, donor_phone)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": success}).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def log_message(self, format, *args):
        # Clean logging
        pass


def run_server(port: int = PORT, host: str = HOST):
    current_port = port
    httpd = None
    for attempt in range(10):
        try:
            server_address = (host, current_port)
            httpd = HTTPServer(server_address, NammaRakthaHandler)
            break
        except OSError as e:
            if e.errno == 48:  # Address already in use
                current_port += 1
            else:
                raise e

    if not httpd:
        print(f"Could not bind to any port starting from {port}")
        return

    print(f"\n🚀 NammaRaktha Mobile-First Web Server running on http://{host}:{current_port}")
    print("Press Ctrl+C to terminate.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down NammaRaktha Web Server...")
        httpd.server_close()


if __name__ == "__main__":
    run_server()
