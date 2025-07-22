package main

import (
	"encoding/json"
	"log"
	"net/http"
)

type LogEntry struct {
	Timestamp string `json:"timestamp"`
	Service   string `json:"service"`
	Level     string `json:"level"`
	Message   string `json:"message"`
}

func handleLogs(w http.ResponseWriter, r *http.Request) {
	var entry LogEntry
	err := json.NewDecoder(r.Body).Decode(&entry)
	if err != nil {
		http.Error(w, "Bad request", http.StatusBadRequest)
		return
	}
	log.Printf("Received log: %+v\n", entry)
	w.WriteHeader(http.StatusAccepted)
}

func main() {
	http.HandleFunc("/logs", handleLogs)
	log.Println("Go server running at :8080")
	log.Fatal(http.ListenAndServe(":8080", nil))
}
