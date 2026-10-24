import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function GET() {
  const cases = await prisma.case.findMany({
    orderBy: { createdAt: "desc" },
    include: { steps: true },
  });
  return NextResponse.json(cases);
}

export async function POST(req: Request) {
  const body = await req.json();
  const { title, plant, product, reportedBy, priority } = body;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const newCase = await prisma.case.create({
    data: { title, plant, product, reportedBy, priority: priority || "Medium" },
  });

  await prisma.auditLog.create({
    data: {
      caseId: (newCase as { id: string }).id,
      stepNum: 0,
      action: "CASE_CREATED",
      after: JSON.stringify({ title, plant, product, reportedBy }),
    },
  });

  return NextResponse.json(newCase, { status: 201 });
}
