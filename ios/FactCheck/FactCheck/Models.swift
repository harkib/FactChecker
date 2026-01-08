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
}

// MARK: - Verified Claims Structure

struct VerifiedClaims: Codable {
    let overall: OverallVerdict
    let claim_results: [ClaimResult]
}

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

