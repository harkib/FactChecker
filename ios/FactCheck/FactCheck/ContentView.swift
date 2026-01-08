//
//  ContentView.swift
//  FactCheck
//
//  Created by harki bains on 12/30/25.
//

import SwiftUI

struct ContentView: View {
    @EnvironmentObject var viewModel: FactCheckViewModel
    
    var body: some View {
        NavigationView {
            List {
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
                .padding(.vertical, 8)
                .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
                .listRowSeparator(.hidden)
                
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
                    .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
                    .listRowSeparator(.hidden)
                }
                
                // Jobs List
                if viewModel.jobs.isEmpty {
                    VStack(spacing: 16) {
                        Image(systemName: "tray")
                            .font(.system(size: 48))
                            .foregroundColor(.gray)
                        Text("No jobs yet")
                            .font(.headline)
                            .foregroundColor(.secondary)
                        Text("Submit a video URL to get started")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 40)
                    .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
                    .listRowSeparator(.hidden)
                } else {
                    ForEach(viewModel.jobs, id: \.id) { job in
                        JobCardView(job: job, isExpanded: viewModel.isJobExpanded(job.id)) {
                            if job.status == "completed" {
                                viewModel.toggleJobExpansion(jobId: job.id)
                            }
                        }
                        .listRowInsets(EdgeInsets(top: 4, leading: 16, bottom: 4, trailing: 16))
                        .listRowSeparator(.hidden)
                    }
                }
            }
            .listStyle(PlainListStyle())
            .refreshable {
                await viewModel.refreshJobs()
            }
            .navigationTitle("Fact Checker")
        }
    }
}

// MARK: - Job Card View

struct JobCardView: View {
    let job: JobResponse
    let isExpanded: Bool
    let onTap: () -> Void
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Collapsed Header
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(job.title ?? "Untitled")
                        .font(.headline)
                        .lineLimit(2)
                    
                    HStack(spacing: 8) {
                        // Status Badge
                        StatusBadge(status: job.status)
                        
                        // Verdict Badge (if completed)
                        if job.status == "completed", let verifiedClaims = job.verified_claims {
                            VerdictBadge(verdict: verifiedClaims.overall.verdict)
                        }
                    }
                }
                
                Spacer()
                
                // Expand/Collapse Indicator (only if completed)
                if job.status == "completed" {
                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .foregroundColor(.secondary)
                        .font(.caption)
                }
            }
            .contentShape(Rectangle())
            .onTapGesture {
                onTap()
            }
            
            // Expanded Content (only if completed and expanded)
            if job.status == "completed" && isExpanded {
                Divider()
                
                if let verifiedClaims = job.verified_claims {
                    // Summary Section
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Summary")
                            .font(.subheadline)
                            .fontWeight(.semibold)
                            .foregroundColor(.secondary)
                        
                        Text(verifiedClaims.overall.summary)
                            .font(.body)
                            .foregroundColor(.primary)
                    }
                    .padding(.vertical, 8)
                    
                    // Claims Section
                    if let claims = job.claims, !claims.isEmpty {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Claims")
                                .font(.subheadline)
                                .fontWeight(.semibold)
                                .foregroundColor(.secondary)
                            
                            ForEach(Array(zip(claims.indices, claims)), id: \.0) { index, claim in
                                if index < verifiedClaims.claim_results.count {
                                    ClaimCardView(
                                        claim: claim,
                                        claimResult: verifiedClaims.claim_results[index]
                                    )
                                }
                            }
                        }
                        .padding(.vertical, 8)
                    }
                }
                
                // Open URL Button
                if let url = URL(string: job.video_url) {
                    Button(action: {
                        UIApplication.shared.open(url)
                    }) {
                        HStack {
                            Image(systemName: "safari")
                            Text("Open Original URL")
                        }
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color.blue)
                        .foregroundColor(.white)
                        .cornerRadius(10)
                    }
                    .padding(.top, 8)
                }
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(color: Color.black.opacity(0.1), radius: 4, x: 0, y: 2)
    }
}

// MARK: - Claim Card View

struct ClaimCardView: View {
    let claim: String
    let claimResult: ClaimResult
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(claim)
                .font(.subheadline)
                .fontWeight(.medium)
                .foregroundColor(.primary)
            
            HStack {
                VerdictBadge(verdict: claimResult.verdict)
                
                Spacer()
                
                Text(String(format: "%.0f%%", claimResult.confidence * 100))
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            Text(claimResult.rationale)
                .font(.caption)
                .foregroundColor(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .cornerRadius(8)
    }
}

// MARK: - Status Badge

struct StatusBadge: View {
    let status: String
    
    var body: some View {
        Text(status.capitalized)
            .font(.caption)
            .fontWeight(.semibold)
            .foregroundColor(statusColor(for: status))
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(statusColor(for: status).opacity(0.2))
            .cornerRadius(6)
    }
    
    private func statusColor(for status: String) -> Color {
        switch status.lowercased() {
        case "completed":
            return .green
        case "failed":
            return .red
        case "pending", "processing":
            return .orange
        default:
            return .gray
        }
    }
}

// MARK: - Verdict Badge

struct VerdictBadge: View {
    let verdict: String
    
    var body: some View {
        Text(verdict.replacingOccurrences(of: "_", with: " ").capitalized)
            .font(.caption)
            .fontWeight(.semibold)
            .foregroundColor(verdictColor(for: verdict))
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(verdictColor(for: verdict).opacity(0.2))
            .cornerRadius(6)
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
        .environmentObject(FactCheckViewModel())
}
