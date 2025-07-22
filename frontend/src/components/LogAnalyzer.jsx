import React, { useState } from "react";
import { analyzeLogs } from "../services/analyzeService";
import { fetchAnalysis } from "../services/logService";  // ✅ new import

export default function LogAnalyzer() {
  const [logInput, setLogInput] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleAnalyze = async () => {
    try {
      setLoading(true);

      const logs = logInput.trim().split("\n").map((line, index) => ({
        timestamp: new Date().toISOString(),
        level: line.includes("ERROR") ? "ERROR" : "INFO",
        message: line,
        trace_id: `trace-${index}`
      }));

      const response = await analyzeLogs(logs);
      setResult(response);

      // Optional: fetch analysis from Redis for first trace
      const redisAnalysis = await fetchAnalysis(`trace-0`);
      console.log("Fetched Redis Analysis:", redisAnalysis);

    } catch (error) {
      setResult({ error: error.message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white p-4 rounded shadow">
      <h3 className="text-lg font-semibold mb-2">Analyze Logs</h3>
      <textarea
        className="w-full h-40 p-2 border rounded mb-4"
        placeholder="Paste logs here (one per line)..."
        value={logInput}
        onChange={(e) => setLogInput(e.target.value)}
      />
      <button
        onClick={handleAnalyze}
        className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
        disabled={loading}
      >
        {loading ? "Analyzing..." : "Analyze Logs"}
      </button>
      {result && (
        <div className="mt-4 bg-gray-100 p-3 rounded text-sm">
          <h4 className="font-semibold mb-1">AI Result:</h4>
          <pre className="whitespace-pre-wrap">{JSON.stringify(result, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}
import React, { useState } from "react";
import { analyzeLogs } from "../services/analyzeService";
import { fetchAnalysis } from "../services/logService";  // ✅ new import

export default function LogAnalyzer() {
  const [logInput, setLogInput] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleAnalyze = async () => {
    try {
      setLoading(true);

      const logs = logInput.trim().split("\n").map((line, index) => ({
        timestamp: new Date().toISOString(),
        level: line.includes("ERROR") ? "ERROR" : "INFO",
        message: line,
        trace_id: `trace-${index}`
      }));

      const response = await analyzeLogs(logs);
      setResult(response);

      // Optional: fetch analysis from Redis for first trace
      const redisAnalysis = await fetchAnalysis(`trace-0`);
      console.log("Fetched Redis Analysis:", redisAnalysis);

    } catch (error) {
      setResult({ error: error.message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white p-4 rounded shadow">
      <h3 className="text-lg font-semibold mb-2">Analyze Logs</h3>
      <textarea
        className="w-full h-40 p-2 border rounded mb-4"
        placeholder="Paste logs here (one per line)..."
        value={logInput}
        onChange={(e) => setLogInput(e.target.value)}
      />
      <button
        onClick={handleAnalyze}
        className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
        disabled={loading}
      >
        {loading ? "Analyzing..." : "Analyze Logs"}
      </button>
      {result && (
        <div className="mt-4 bg-gray-100 p-3 rounded text-sm">
          <h4 className="font-semibold mb-1">AI Result:</h4>
          <pre className="whitespace-pre-wrap">{JSON.stringify(result, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}
