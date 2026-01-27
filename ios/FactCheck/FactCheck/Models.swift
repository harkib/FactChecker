//
//  Models.swift
//  FactCheck
//
//  Created on 12/30/25.
//

import Foundation

// MARK: - Request Models

struct CreateJobRequest: Codable {
    let video_url: String
}

// MARK: - Response Models

struct CreateJobResponse: Codable {
    let job_id: String
    let status: String
}

struct JobResponse: Codable {
    let id: String
    let video_url: String
    let status: String
    let created_at: String
    let updated_at: String
    let video_s3_key: String?
    let transcript_s3_key: String?
    let frames_s3_prefix: String?
    let claims: [String]?
    let verified_claims: VerifiedClaims?
    let error_message: String?
    let client_id: String
    let title: String?
    let failed: Bool?
}

// MARK: - Verified Claims Structure

struct VerifiedClaims: Codable {
    let title: String
    let verifications: [Verification]
    
    // CodingKeys for both old and new formats
    enum CodingKeys: String, CodingKey {
        case title
        case verifications
        case overall
        case claim_results
    }
    
    // Backward compatibility: handle both old and new formats
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        
        // Try new format first (title + verifications)
        if container.contains(.title) && container.contains(.verifications) {
            self.title = try container.decode(String.self, forKey: .title)
            self.verifications = try container.decode([Verification].self, forKey: .verifications)
            return
        }
        
        // Fall back to old format (overall + claim_results)
        if container.contains(.overall) && container.contains(.claim_results) {
            let overall = try container.decode(OverallVerdict.self, forKey: .overall)
            let claimResults = try container.decode([ClaimResult].self, forKey: .claim_results)
            
            // Extract title from overall summary or use empty string
            self.title = overall.summary.isEmpty ? "" : overall.summary
            
            // Transform claim_results to verifications format
            // Note: Old format doesn't have claim text in claim_results, so we use empty string
            self.verifications = claimResults.map { result in
                Verification(
                    claim: "",
                    verdict: result.verdict,
                    rationale: result.rationale
                )
            }
            return
        }
        
        // If neither format matches, throw decoding error
        throw DecodingError.dataCorrupted(
            DecodingError.Context(
                codingPath: decoder.codingPath,
                debugDescription: "Unable to decode VerifiedClaims in either old or new format"
            )
        )
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(title, forKey: .title)
        try container.encode(verifications, forKey: .verifications)
    }
}

struct Verification: Codable {
    let claim: String
    let verdict: String
    let rationale: String
}

// MARK: - Legacy Structures (for backward compatibility decoding only)

struct OverallVerdict: Codable {
    let verdict: String
    let confidence: Double
    let summary: String
}

struct ClaimResult: Codable {
    let verdict: String
    let confidence: Double
    let rationale: String
}

// MARK: - Upload Models

struct CreateUploadJobResponse: Codable {
    let job_id: String
    let upload_url: String
    let expires_in: Int
}

struct GetUploadUrlResponse: Codable {
    let upload_url: String
    let expires_in: Int
}
