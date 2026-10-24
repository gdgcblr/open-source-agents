/** A timed-out logging operation has an unknown storage outcome. */
export class SinkTimeout extends Error {}

/** Args: callback and timeout. Returns: callback result. Raises: original error or SinkTimeout. */
export async function withinTimeout<Result>(
  operation: () => Result | Promise<Result>,
  milliseconds: number,
): Promise<Result> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      Promise.resolve().then(operation),
      new Promise<never>((_resolve, reject) => {
        timer = setTimeout(
          () => reject(new SinkTimeout('Sink operation timed out.')),
          milliseconds,
        );
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}
