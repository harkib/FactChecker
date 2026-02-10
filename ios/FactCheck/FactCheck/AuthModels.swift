//
//  AuthModels.swift
//  FactCheck
//
//  Created on 2/6/26.
//

import Foundation

// MARK: - Request Models

struct AppleSignInRequest: Codable {
    let identity_token: String
    let authorization_code: String
}

// MARK: - Response Models

struct AppleSignInResponse: Codable {
    let auth_key: String
}
