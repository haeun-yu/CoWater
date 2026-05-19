export async function sendMessage(input: string): Promise<{ message: string; type: string }> {
  return {
    message: `Received: ${input}`,
    type: 'info',
  };
}

