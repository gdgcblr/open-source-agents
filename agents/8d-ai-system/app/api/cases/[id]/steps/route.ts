import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id: caseId } = await params;
  const { stepNumber, content, aiSuggested, action } = await req.json();

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const existing: any = await prisma.dStep.findUnique({
    where: { caseId_stepNumber: { caseId, stepNumber } },
  });

  let step;
  if (existing) {
    const before = existing.content;
    step = await prisma.dStep.update({
      where: { caseId_stepNumber: { caseId, stepNumber } },
      data: {
        content: JSON.stringify(content),
        aiSuggested: aiSuggested ? JSON.stringify(aiSuggested) : existing.aiSuggested,
        updatedAt: new Date(),
      },
    });
    await prisma.auditLog.create({
      data: {
        caseId,
        stepNum: stepNumber,
        action: action || "HUMAN_EDITED",
        before,
        after: JSON.stringify(content),
      },
    });
  } else {
    step = await prisma.dStep.create({
      data: {
        caseId,
        stepNumber,
        content: JSON.stringify(content),
        aiSuggested: aiSuggested ? JSON.stringify(aiSuggested) : null,
      },
    });
    await prisma.auditLog.create({
      data: {
        caseId,
        stepNum: stepNumber,
        action: action || "AI_SUGGESTED",
        after: JSON.stringify(content),
      },
    });
  }

  return NextResponse.json(step);
}

export async function PUT(
  req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id: caseId } = await params;
  const { stepNumber, approvedBy } = await req.json();

  const step = await prisma.dStep.update({
    where: { caseId_stepNumber: { caseId, stepNumber } },
    data: { approved: true, approvedBy: approvedBy || "Quality Engineer", approvedAt: new Date() },
  });

  await prisma.auditLog.create({
    data: {
      caseId,
      stepNum: stepNumber,
      action: "APPROVED",
      userId: approvedBy || "Quality Engineer",
    },
  });

  const nextStep = stepNumber + 1;
  if (nextStep <= 8) {
    await prisma.case.update({ where: { id: caseId }, data: { status: `D${nextStep}` } });
  } else {
    await prisma.case.update({ where: { id: caseId }, data: { status: "CLOSED" } });
  }

  return NextResponse.json(step);
}
