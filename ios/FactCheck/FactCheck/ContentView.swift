//
//  ContentView.swift
//  FactCheck
//
//  Created by harki bains on 12/30/25.
//

import SwiftUI

// MARK: - Citation Model

struct Citation: Identifiable {
    let id: Int
    let url: String
    let originalText: String
}

// MARK: - Citation Parser

extension String {
    func parseCitations() -> (cleanedText: String, citations: [Citation]) {
        var citations: [Citation] = []
        var cleanedText = self
        var citationNumber = 1
        
        // Regex pattern to match markdown links: [text](url) or ([text](url))
        // This pattern handles both formats:
        // - [text](url) - standard markdown
        // - ([text](url)) - OpenAI format with outer parentheses
        let pattern = #"(\(?)\[([^\]]+)\]\(([^\)]+)\)(\)?)"#
        
        guard let regex = try? NSRegularExpression(pattern: pattern, options: []) else {
            return (self, [])
        }
        
        let nsString = self as NSString
        let matches = regex.matches(in: self, options: [], range: NSRange(location: 0, length: nsString.length))
        
        // Process matches in reverse order to maintain correct indices when replacing
        for match in matches.reversed() {
            if match.numberOfRanges >= 4 {
                let originalTextRange = match.range
                let linkTextRange = match.range(at: 2) // Group 2 is the link text
                let urlRange = match.range(at: 3) // Group 3 is the URL
                
                if let urlString = Range(urlRange, in: self) {
                    let url = String(self[urlString])
                    let originalText = nsString.substring(with: linkTextRange)
                    
                    let citation = Citation(
                        id: citationNumber,
                        url: url,
                        originalText: originalText
                    )
                    citations.insert(citation, at: 0) // Insert at beginning since we're processing in reverse
                    
                    // Replace the markdown link (including outer parentheses if present) with the citation number
                    let replacement = "[\(citationNumber)]"
                    if let range = Range(originalTextRange, in: cleanedText) {
                        cleanedText.replaceSubrange(range, with: replacement)
                    }
                    
                    citationNumber += 1
                }
            }
        }
        
        return (cleanedText, citations)
    }
}

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
                        JobCardView(
                            job: job,
                            isExpanded: viewModel.isJobExpanded(job.id),
                            viewModel: viewModel
                        ) {
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
    let viewModel: FactCheckViewModel
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
                        
                        // Verdict Badge (if completed) - show first verification verdict
                        if job.status == "completed", let verifiedClaims = job.verified_claims, let firstVerdict = verifiedClaims.verifications.first?.verdict {
                            VerdictBadge(verdict: firstVerdict)
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
                    // Verifications Section (replaces claims + claim_results)
                    if !verifiedClaims.verifications.isEmpty {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Verifications")
                                .font(.subheadline)
                                .fontWeight(.semibold)
                                .foregroundColor(.secondary)
                            
                            ForEach(Array(verifiedClaims.verifications.enumerated()), id: \.offset) { index, verification in
                                VerificationCardView(
                                    verification: verification,
                                    verificationId: "\(job.id)-\(index)",
                                    isExpanded: viewModel.isVerificationExpanded("\(job.id)-\(index)")
                                ) {
                                    viewModel.toggleVerificationExpansion(verificationId: "\(job.id)-\(index)")
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

// MARK: - Verification Card View

struct VerificationCardView: View {
    let verification: Verification
    let verificationId: String
    let isExpanded: Bool
    let onTap: () -> Void
    
    private var parsedRationale: (cleanedText: String, citations: [Citation]) {
        verification.rationale.parseCitations()
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Collapsed Header (always visible)
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    if !verification.claim.isEmpty {
                        Text(verification.claim)
                            .font(.subheadline)
                            .fontWeight(.medium)
                            .foregroundColor(.primary)
                    }
                    
                    HStack {
                        VerdictBadge(verdict: verification.verdict)
                        Spacer()
                    }
                }
                
                Spacer()
                
                // Expand/Collapse Indicator
                Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                    .foregroundColor(.secondary)
                    .font(.caption)
            }
            .contentShape(Rectangle())
            .onTapGesture {
                onTap()
            }
            
            // Expanded Content (rationale and citations)
            if isExpanded {
                Divider()
                    .padding(.vertical, 4)
                
                let (cleanedText, citations) = parsedRationale
                
                if !cleanedText.isEmpty {
                    Text(cleanedText)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                
                // Citations Section
                if !citations.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(citations) { citation in
                            CitationView(citation: citation)
                        }
                    }
                    .padding(.top, 8)
                }
            }
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .cornerRadius(8)
    }
}

// MARK: - Citation View

struct CitationView: View {
    let citation: Citation
    
    var body: some View {
        Button(action: {
            if let url = URL(string: citation.url) {
                UIApplication.shared.open(url)
            }
        }) {
            HStack(spacing: 12) {
                // Numbered icon on the left
                ZStack {
                    Circle()
                        .fill(Color.blue.opacity(0.2))
                        .frame(width: 28, height: 28)
                    Text("\(citation.id)")
                        .font(.caption)
                        .fontWeight(.semibold)
                        .foregroundColor(.blue)
                }
                
                // URL text on the right
                Text(citation.url)
                    .font(.caption2)
                    .foregroundColor(.secondary)
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
                
                Spacer()
            }
            .padding(.vertical, 8)
            .padding(.horizontal, 8)
            .background(Color(.tertiarySystemBackground))
            .cornerRadius(6)
        }
        .buttonStyle(PlainButtonStyle())
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
