export type Dialect = 'postgresql' | 'mysql' | 'sqlite'

export interface TableSchema {
  name: string
  columns: string[]
}

export interface SchemaInput {
  tables: TableSchema[]
}

export interface Answer {
  sql: string
  explanation: string
  assumptions: string[]
  risks: string[]
  unverified: true
}

export interface QueryResponse {
  session_id: string
  answer: Answer
  dialect: Dialect
  created_at: string
}

export interface SessionSummary {
  id: string
  title: string
  dialect: Dialect
  updated_at: string
}

export interface SessionDetail extends SessionSummary {
  messages: { question: string; answer: Answer; dialect: Dialect; created_at: string }[]
}
