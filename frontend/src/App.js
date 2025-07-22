import React, { useState } from 'react';
import axios from 'axios';

function App() {
  const [logs, setLogs] = useState('');
  const [results, setResults] = useState([]);

  const handleAnalyze = async () => {
    if (logs.trim() === '') {
      alert("Please enter logs before analyzing.");
      return;
    }

    try {
      const logLines = logs.split('\n').filter(line => line.trim() !== '');
      const traceId = `trace-${Date.now()}`;
      const payload = {
        logs: logLines.map((msg) => ({
          timestamp: new Date().toISOString(),
          level: "ERROR",
          message: msg,
          trace_id: traceId,
        })),
      };

      const response = await axios.post('http://localhost:8000/analyze', payload);
      setResults(response.data.results);
    } catch (error) {
      console.error("Error analyzing logs:", error);
      alert("Failed to analyze logs.");
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 text-gray-900 flex">
      <aside className="w-64 bg-white shadow-lg p-4">
        <h1 className="text-2xl font-bold mb-6">Debug Assistant</h1>
        <nav className="space-y-2">
          <a href="#" className="block px-3 py-2 rounded hover:bg-gray-200">Dashboard</a>
          <a href="#" className="block px-3 py-2 rounded hover:bg-gray-200">Logs</a>
          <a href="#" className="block px-3 py-2 rounded hover:bg-gray-200">Postmortems</a>
        </nav>
      </aside>

      <main className="flex-1 p-6">
        <h2 className="text-xl font-semibold mb-4">Analyze Logs</h2>

        <textarea
          className="w-full p-3 border rounded mb-4 h-40"
          placeholder="Paste logs here..."
          value={logs}
          onChange={(e) => setLogs(e.target.value)}
        />

        <button
          onClick={handleAnalyze}
          className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
        >
          Analyze Logs
        </button>

        <div className="mt-6 space-y-6">
          {results.length > 0 ? (
            results.map((res, idx) => (
              <div key={idx} className="bg-white p-4 rounded shadow">
                <p className="font-semibold mb-2">Log:</p>
                <pre className="bg-gray-100 p-2 rounded whitespace-pre-wrap mb-4">
                  {res.log_text}
                </pre>

                <p className="font-semibold mb-1">Root Cause Analysis:</p>
                <pre className="bg-blue-50 p-2 rounded whitespace-pre-wrap mb-4">
                  {res.agents.root_cause_agent || 'No analysis provided.'}
                </pre>

                <p className="font-semibold mb-1">Fix Suggestions:</p>
                <pre className="bg-green-50 p-2 rounded whitespace-pre-wrap mb-4">
                  {res.agents.fix_suggester_agent || 'No suggestions provided.'}
                </pre>

                <p className="font-semibold mb-1">Impact Analysis:</p>
                <pre className="bg-yellow-50 p-2 rounded whitespace-pre-wrap">
                  {res.agents.impact_analyzer_agent || 'No impact analysis provided.'}
                </pre>
              </div>
            ))
          ) : (
            <p className="text-gray-500">No analysis results yet. Paste logs and click Analyze.</p>
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
