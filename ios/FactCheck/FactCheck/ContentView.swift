//
//  ContentView.swift
//  FactCheck
//
//  Created by harki bains on 12/30/25.
//

import SwiftUI

struct ContentView: View {
    @StateObject private var viewModel = FactCheckViewModel()
    
    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 20) {
                    // URL Input Section
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Video URL")
                            .font(.headline)
                        
                        TextField("Enter video URL", text: $viewModel.videoURL)
                            .textFieldStyle(RoundedBorderTextFieldStyle())
                            .autocapitalization(.none)
                            .autocorrectionDisabled()
                            .keyboardType(.URL)
                        
                        Button(action: {
                            viewModel.submitJob()
                        }) {
                            HStack {
                                if viewModel.isLoading {
                                    ProgressView()
                                        .progressViewStyle(CircularProgressViewStyle(tint: .white))
                                }
                                Text(viewModel.isLoading ? "Processing..." : "Submit")
                            }
                            .frame(maxWidth: .infinity)
                            .padding()
                            .background(viewModel.isLoading || viewModel.videoURL.isEmpty ? Color.gray : Color.blue)
                            .foregroundColor(.white)
                            .cornerRadius(10)
                        }
                        .disabled(viewModel.isLoading || viewModel.videoURL.isEmpty)
                    }
                    .padding()
                    
                    // Status Display
                    if let status = viewModel.jobStatus {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Status")
                                .font(.headline)
                            Text(status.capitalized)
                                .font(.subheadline)
                                .padding(8)
                                .background(statusBackgroundColor(for: status))
                                .cornerRadius(8)
                        }
                        .padding(.horizontal)
                    }
                    
                    // Error Message
                    if let errorMessage = viewModel.errorMessage {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Error")
                                .font(.headline)
                            Text(errorMessage)
                                .font(.subheadline)
                                .foregroundColor(.red)
                                .padding()
                                .background(Color.red.opacity(0.1))
                                .cornerRadius(8)
                        }
                        .padding(.horizontal)
                    }
                    
                    // Results Section
                    if let jobResponse = viewModel.jobResponse, jobResponse.status == "completed" {
                        if let verifiedClaims = jobResponse.verified_claims {
                            VStack(alignment: .leading, spacing: 16) {
                                Text("Fact Check Results")
                                    .font(.title2)
                                    .fontWeight(.bold)
                                
                                // Overall Verdict
                                VStack(alignment: .leading, spacing: 8) {
                                    Text("Overall Verdict")
                                        .font(.headline)
                                    HStack {
                                        Text(verifiedClaims.overall.verdict)
                                            .font(.title3)
                                            .fontWeight(.semibold)
                                            .foregroundColor(verdictColor(for: verifiedClaims.overall.verdict))
                                        Spacer()
                                        Text(String(format: "%.0f%%", verifiedClaims.overall.confidence * 100))
                                            .font(.subheadline)
                                            .foregroundColor(.secondary)
                                    }
                                    Text(verifiedClaims.overall.summary)
                                        .font(.body)
                                        .foregroundColor(.secondary)
                                }
                                .padding()
                                .background(Color.gray.opacity(0.1))
                                .cornerRadius(10)
                                
                                // Claims Results
                                if let claims = jobResponse.claims, !claims.isEmpty {
                                    Text("Claim Details")
                                        .font(.headline)
                                    
                                    ForEach(Array(zip(claims.indices, claims)), id: \.0) { index, claim in
                                        if index < verifiedClaims.claim_results.count {
                                            let claimResult = verifiedClaims.claim_results[index]
                                            VStack(alignment: .leading, spacing: 8) {
                                                Text(claim)
                                                    .font(.subheadline)
                                                    .fontWeight(.medium)
                                                
                                                HStack {
                                                    Text(claimResult.verdict)
                                                        .font(.caption)
                                                        .fontWeight(.semibold)
                                                        .foregroundColor(verdictColor(for: claimResult.verdict))
                                                        .padding(.horizontal, 8)
                                                        .padding(.vertical, 4)
                                                        .background(verdictColor(for: claimResult.verdict).opacity(0.2))
                                                        .cornerRadius(6)
                                                    
                                                    Spacer()
                                                    
                                                    Text(String(format: "%.0f%%", claimResult.confidence * 100))
                                                        .font(.caption)
                                                        .foregroundColor(.secondary)
                                                }
                                                
                                                Text(claimResult.rationale)
                                                    .font(.caption)
                                                    .foregroundColor(.secondary)
                                            }
                                            .padding()
                                            .background(Color.white)
                                            .cornerRadius(8)
                                            .shadow(color: Color.black.opacity(0.05), radius: 2, x: 0, y: 1)
                                        }
                                    }
                                }
                            }
                            .padding()
                        } else {
                            Text("No verification results available")
                                .foregroundColor(.secondary)
                                .padding()
                        }
                    }
                }
                .padding(.vertical)
            }
            .navigationTitle("Fact Checker")
        }
    }
    
    // MARK: - Helper Methods
    
    private func statusBackgroundColor(for status: String) -> Color {
        switch status.lowercased() {
        case "completed":
            return Color.green.opacity(0.2)
        case "failed":
            return Color.red.opacity(0.2)
        case "pending", "processing":
            return Color.orange.opacity(0.2)
        default:
            return Color.gray.opacity(0.2)
        }
    }
    
    private func verdictColor(for verdict: String) -> Color {
        switch verdict.uppercased() {
        case "TRUE":
            return .green
        case "FALSE":
            return .red
        case "PARTIALLY_TRUE":
            return .orange
        case "UNVERIFIABLE", "DISPUTED":
            return .yellow
        case "NOT_FACTUAL":
            return .gray
        default:
            return .primary
        }
    }
}

#Preview {
    ContentView()
}
