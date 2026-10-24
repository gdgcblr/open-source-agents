import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const c = await prisma.case.findUnique({
    where: { id },
    include: { steps: { orderBy: { stepNumber: "asc" } }, auditLogs: { orderBy: { createdAt: "asc" } } },
  });
  if (!c) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json(c);
}

export async function PATCH(
  req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const body = await req.json();
  const updated = await prisma.case.update({ where: { id }, data: body });
  return NextResponse.json(updated);
}
