import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

const SAMPLE_CASES = [
  {
    title: "Surface finish defect on aluminum housing — Batch 2024-Q3",
    plant: "Plant B - Haridwar",
    product: "Aluminum Gear Housing",
    reportedBy: "Amita Sharma",
    priority: "High",
    status: "CLOSED",
    steps: [
      {
        stepNumber: 1,
        content: JSON.stringify({
          teamLeader: "Rajiv Mehta (Senior Quality Engineer)",
          members: [
            { name: "Priya Nair", role: "Process Engineer", department: "Manufacturing" },
            { name: "Suresh Gupta", role: "Supplier Quality", department: "Procurement" },
            { name: "Anita Roy", role: "Machine Operator", department: "Production" },
            { name: "Deepak Singh", role: "Maintenance Tech", department: "Maintenance" },
          ],
          meetingDate: "2024-07-15",
          rationale: "Cross-functional team covering process, supplier, and maintenance domains.",
        }),
        approved: true,
        approvedBy: "Quality Engineer",
      },
      {
        stepNumber: 2,
        content: JSON.stringify({
          problemStatement: "Surface roughness Ra > 3.2 µm on machined face of housing, spec requires Ra ≤ 1.6 µm",
          what: "Surface finish exceeds specification on inner bore face",
          when: "First detected during incoming inspection on 2024-07-12",
          where: "CNC machining line 3, aluminum housing inner bore",
          who: "Downstream assembly team and customer",
          howMany: "340 units affected out of 800 units in batch",
          isNot: "Not a dimensional issue, not affecting all surfaces, not batch-wide",
          severity: "High",
          customerImpact: "Risk of premature wear in field, potential warranty claims",
        }),
        approved: true,
        approvedBy: "Quality Engineer",
      },
      {
        stepNumber: 4,
        content: JSON.stringify({
          rootCause: "Worn cutting insert not replaced on schedule due to manual tracking gap — insert ran 180% beyond rated life",
          fishbone: {
            effect: "Surface finish defect Ra > 3.2 µm",
            categories: {
              Man: ["Operator not alerted to insert life", "Inconsistent monitoring"],
              Machine: ["No automated insert life counter", "Vibration sensor offline"],
              Material: ["Insert grade change by supplier", "Aluminum alloy hardness variation"],
              Method: ["Manual insert tracking in paper log", "No real-time SPC monitoring"],
              Measurement: ["Ra checked only at end of batch", "Gauge calibration overdue"],
              Environment: ["Temperature variation in machine bay", "Coolant contamination"],
            },
          },
          fiveWhy: [
            { why: "Why was surface finish out of spec?", answer: "Cutting insert was worn beyond its rated life" },
            { why: "Why was the insert used beyond rated life?", answer: "Manual tracking log was not updated after last shift" },
            { why: "Why was the log not updated?", answer: "Operator changed shift without completing handover checklist" },
            { why: "Why was the handover incomplete?", answer: "No mandatory digital sign-off enforced in the system" },
            { why: "Why is there no digital sign-off?", answer: "Insert life management relies entirely on paper-based process" },
          ],
          escapeCause: "End-of-batch inspection missed because Ra measurement was only at final stage, not mid-batch",
        }),
        approved: true,
        approvedBy: "Quality Engineer",
      },
    ],
  },
  {
    title: "Oil leak detected at cylinder head gasket joint — Field returns",
    plant: "Plant A - Dharuhera",
    product: "Engine Cylinder Head",
    reportedBy: "Vikram Khanna",
    priority: "Critical",
    status: "CLOSED",
    steps: [
      {
        stepNumber: 1,
        content: JSON.stringify({
          teamLeader: "Neha Joshi (Quality Lead)",
          members: [
            { name: "Arun Kumar", role: "Design Engineer", department: "R&D" },
            { name: "Meera Pillai", role: "Supplier Dev", department: "Procurement" },
            { name: "Rahul Tiwari", role: "Assembly Line Lead", department: "Production" },
            { name: "Sanjay Verma", role: "Field Service", department: "Service" },
          ],
          meetingDate: "2024-09-03",
          rationale: "Oil leak requires design, supplier, assembly, and field perspectives.",
        }),
        approved: true,
        approvedBy: "Quality Engineer",
      },
      {
        stepNumber: 2,
        content: JSON.stringify({
          problemStatement: "Engine oil leak from cylinder head gasket joint reported in 23 field units within first 5000 km",
          what: "Oil seeping from head gasket interface at rear cylinder",
          when: "Reported between 1000–5000 km service life",
          where: "Rear cylinder head, between head and block mating surface",
          who: "End customers, service network",
          howMany: "23 field units, potentially 450+ units at risk from same batch",
          isNot: "Not front cylinder, not coolant leak, not all production lots",
          severity: "Critical",
          customerImpact: "Severe — safety risk, warranty cost, brand reputation damage",
        }),
        approved: true,
        approvedBy: "Quality Engineer",
      },
      {
        stepNumber: 4,
        content: JSON.stringify({
          rootCause: "Gasket embossment height 0.08mm below specification due to tooling wear at supplier, causing insufficient sealing load",
          fishbone: {
            effect: "Oil leak at cylinder head gasket",
            categories: {
              Man: ["Incoming inspection not checking embossment height", "Supplier audit overdue"],
              Machine: ["Gasket press tooling wear at supplier", "Torque wrench calibration drift"],
              Material: ["Gasket embossment height below spec", "Gasket material lot variation"],
              Method: ["Embossment height not in incoming inspection plan", "Torque spec not reviewed after redesign"],
              Measurement: ["No 100% embossment height check", "CMM measurement plan gap"],
              Environment: ["Thermal cycling in engine bay accelerating failure", "Oil viscosity grade mismatch"],
            },
          },
          fiveWhy: [
            { why: "Why is oil leaking from the head gasket?", answer: "Insufficient clamping load at the sealing surface" },
            { why: "Why is clamping load insufficient?", answer: "Gasket embossment height is 0.08mm below specification" },
            { why: "Why is the embossment height below spec?", answer: "Gasket press tooling at supplier wore beyond acceptable limit" },
            { why: "Why was tooling wear not detected?", answer: "Supplier's dimensional check frequency was reduced due to cost pressure" },
            { why: "Why was our incoming inspection not catching this?", answer: "Embossment height was not included in the incoming inspection control plan" },
          ],
          escapeCause: "Embossment height was not in incoming inspection plan — gap in control plan review after design change",
        }),
        approved: true,
        approvedBy: "Quality Engineer",
      },
    ],
  },
];

async function main() {
  console.log("Seeding database...");

  for (const c of SAMPLE_CASES) {
    const created = await prisma.case.create({
      data: {
        title: c.title,
        plant: c.plant,
        product: c.product,
        reportedBy: c.reportedBy,
        priority: c.priority,
        status: c.status,
      },
    });

    for (const s of c.steps) {
      await prisma.dStep.create({
        data: {
          caseId: created.id,
          stepNumber: s.stepNumber,
          content: s.content,
          aiSuggested: s.content,
          approved: s.approved,
          approvedBy: s.approvedBy,
          approvedAt: s.approved ? new Date() : null,
        },
      });

      await prisma.auditLog.create({
        data: {
          caseId: created.id,
          stepNum: s.stepNumber,
          action: "AI_SUGGESTED",
          after: s.content,
        },
      });

      if (s.approved) {
        await prisma.auditLog.create({
          data: {
            caseId: created.id,
            stepNum: s.stepNumber,
            action: "APPROVED",
            userId: s.approvedBy || "Quality Engineer",
          },
        });
      }
    }

    console.log(`Created: ${created.title}`);
  }

  console.log("Seeding complete.");
}

main()
  .catch(console.error)
  .finally(() => prisma.$disconnect());
