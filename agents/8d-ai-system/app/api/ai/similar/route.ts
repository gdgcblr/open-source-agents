import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function POST(req: Request) {
  const { title, description } = await req.json();
  const searchTerm = (title + " " + (description || "")).toLowerCase();

  const allCases = await prisma.case.findMany({
    include: { steps: true },
    where: { status: "CLOSED" },
    take: 50,
  });

  const scored = (allCases as Record<string, unknown>[])
    .map((c) => {
      const text = ((c.title as string) + " " + (c.product as string) + " " + (c.plant as string)).toLowerCase();
      const words = searchTerm.split(" ").filter(Boolean);
      const score = words.reduce((acc: number, w: string) => acc + (text.includes(w) ? 1 : 0), 0);
      return { ...c, score };
    })
    .filter((c) => c.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 3);

  return NextResponse.json(scored);
}
