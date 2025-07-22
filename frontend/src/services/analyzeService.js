export async function analyzeLogs(logs) {
  const response = await fetch("http://localhost:8000/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      logs,
      model: "gpt-4o-mini"
    }),
  });

  if (!response.ok) {
    throw new Error("Failed to fetch analysis");
  }

  return response.json();
}
