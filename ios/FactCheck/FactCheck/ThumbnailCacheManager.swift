//
//  ThumbnailCacheManager.swift
//  FactCheck
//
//  Created on 2/6/26.
//

import Foundation
import UIKit

/// Manages thumbnail caching using job_id as the cache key
class ThumbnailCacheManager {
    static let shared = ThumbnailCacheManager()
    
    private let memoryCache = NSCache<NSString, UIImage>()
    private let cacheDirectory: URL
    
    private init() {
        // Configure memory cache
        memoryCache.countLimit = 100 // Limit to 100 thumbnails in memory
        memoryCache.totalCostLimit = 50 * 1024 * 1024 // 50MB limit
        
        // Setup disk cache directory
        let fileManager = FileManager.default
        let cacheDir = fileManager.urls(for: .cachesDirectory, in: .userDomainMask).first!
        cacheDirectory = cacheDir.appendingPathComponent("thumbnails", isDirectory: true)
        
        // Create directory if it doesn't exist
        try? fileManager.createDirectory(at: cacheDirectory, withIntermediateDirectories: true)
    }
    
    /// Get the file path for a cached thumbnail
    private func getCachePath(jobId: String) -> URL {
        // Sanitize jobId to be filesystem-safe
        let sanitizedJobId = jobId.replacingOccurrences(of: "/", with: "_")
        return cacheDirectory.appendingPathComponent("\(sanitizedJobId).jpg")
    }
    
    /// Check if a thumbnail is cached (in memory or on disk)
    func hasCachedThumbnail(jobId: String) -> Bool {
        let key = NSString(string: jobId)
        
        // Check memory cache first
        if memoryCache.object(forKey: key) != nil {
            return true
        }
        
        // Check disk cache
        let cachePath = getCachePath(jobId: jobId)
        return FileManager.default.fileExists(atPath: cachePath.path)
    }
    
    /// Retrieve a cached thumbnail
    func getCachedThumbnail(jobId: String) -> UIImage? {
        let key = NSString(string: jobId)
        
        // Check memory cache first
        if let cachedImage = memoryCache.object(forKey: key) {
            return cachedImage
        }
        
        // Check disk cache
        let cachePath = getCachePath(jobId: jobId)
        guard FileManager.default.fileExists(atPath: cachePath.path),
              let imageData = try? Data(contentsOf: cachePath),
              let image = UIImage(data: imageData) else {
            return nil
        }
        
        // Store in memory cache for faster access next time
        memoryCache.setObject(image, forKey: key)
        return image
    }
    
    /// Store a thumbnail in both memory and disk cache
    func storeThumbnail(jobId: String, image: UIImage) {
        let key = NSString(string: jobId)
        
        // Store in memory cache
        memoryCache.setObject(image, forKey: key)
        
        // Store on disk
        let cachePath = getCachePath(jobId: jobId)
        if let imageData = image.jpegData(compressionQuality: 0.8) {
            try? imageData.write(to: cachePath)
        }
    }
    
    /// Clear all cached thumbnails (useful for debugging or cache management)
    func clearCache() {
        memoryCache.removeAllObjects()
        try? FileManager.default.removeItem(at: cacheDirectory)
        try? FileManager.default.createDirectory(at: cacheDirectory, withIntermediateDirectories: true)
    }
}
