// src/services/logService.js

import axios from 'axios';

export async function fetchAnalysis(traceId) {
  try {
    const response = await axios.get(`http://localhost:8000/logs/${traceId}`);
    return response.data;
  } catch (err) {
    console.error('Failed to fetch analysis:', err);
    return null;
  }
}
