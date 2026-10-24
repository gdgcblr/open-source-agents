export interface GenerateOptions {
  /** Ask the provider for JSON output when it supports a native JSON mode. */
  json?: boolean;
}

export interface ModelProvider {
  readonly providerName: string;
  readonly modelName: string;
  generateText(prompt: string, options?: GenerateOptions): Promise<string>;
}
