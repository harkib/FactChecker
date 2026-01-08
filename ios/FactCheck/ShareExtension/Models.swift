//
//  Models.swift
//  ShareExtension
//
//  Created on 1/8/26.
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

