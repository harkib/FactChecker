//
//  ShareViewController.swift
//  ShareExtension
//
//  Created by harki bains on 1/8/26.
//

import UIKit
import UniformTypeIdentifiers

class ShareViewController: UIViewController {
    
    private var hasStarted = false
    private let apiService = APIService.shared
    
    /// Seconds to show "Started" before auto-dismissing the share sheet
    private let secondsBeforeAutoDismissAfterSuccess: TimeInterval = 1
    
    private let statusLabel: UILabel = {
        let label = UILabel()
        label.translatesAutoresizingMaskIntoConstraints = false
        label.font = .systemFont(ofSize: 22, weight: .semibold)
        label.textColor = .label
        label.textAlignment = .center
        label.numberOfLines = 0
        label.text = "Starting..."
        return label
    }()
    
    private let successImageView: UIImageView = {
        let iv = UIImageView()
        iv.translatesAutoresizingMaskIntoConstraints = false
        iv.image = UIImage(systemName: "checkmark.circle.fill")
        iv.tintColor = .systemGreen
        iv.contentMode = .scaleAspectFit
        iv.isHidden = true
        return iv
    }()
    
    private lazy var statusStackView: UIStackView = {
        let stack = UIStackView(arrangedSubviews: [successImageView, statusLabel])
        stack.translatesAutoresizingMaskIntoConstraints = false
        stack.axis = .horizontal
        stack.spacing = 10
        stack.alignment = .center
        return stack
    }()

    override func viewDidLoad() {
        super.viewDidLoad()
        title = ""
        view.backgroundColor = .systemBackground
        
        view.addSubview(statusStackView)
        NSLayoutConstraint.activate([
            successImageView.widthAnchor.constraint(equalToConstant: 48),
            successImageView.heightAnchor.constraint(equalToConstant: 48),
            statusStackView.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            statusStackView.centerYAnchor.constraint(equalTo: view.centerYAnchor),
            statusStackView.leadingAnchor.constraint(greaterThanOrEqualTo: view.safeAreaLayoutGuide.leadingAnchor, constant: 24),
            statusStackView.trailingAnchor.constraint(lessThanOrEqualTo: view.safeAreaLayoutGuide.trailingAnchor, constant: -24)
        ])
        
        navigationItem.leftBarButtonItem = UIBarButtonItem(barButtonSystemItem: .cancel, target: self, action: #selector(cancelTapped))
        
        DispatchQueue.main.async { [weak self] in
            self?.startJobCreation()
        }
    }
    
    @objc private func cancelTapped() {
        extensionContext?.cancelRequest(withError: CancellationError())
    }
    
    private func startJobCreation() {
        guard !hasStarted else { return }
        hasStarted = true
        
        guard let extensionItem = extensionContext?.inputItems.first as? NSExtensionItem else {
            showError("No content found")
            return
        }
        
        statusLabel.text = "Starting..."
        
        extractURL(from: extensionItem) { [weak self] urlString in
            guard let self = self, let url = urlString else {
                DispatchQueue.main.async {
                    self?.showError("No URL found")
                }
                return
            }
            
            Task {
                await self.createJob(url: url)
            }
        }
    }
    
    private func extractURL(from extensionItem: NSExtensionItem, completion: @escaping (String?) -> Void) {
        if let attachments = extensionItem.attachments {
            for attachment in attachments {
                if attachment.hasItemConformingToTypeIdentifier(UTType.url.identifier) {
                    attachment.loadItem(forTypeIdentifier: UTType.url.identifier, options: nil) { (item, error) in
                        if let url = item as? URL {
                            completion(url.absoluteString)
                        } else {
                            completion(nil)
                        }
                    }
                    return
                }
                else if attachment.hasItemConformingToTypeIdentifier(UTType.plainText.identifier) {
                    attachment.loadItem(forTypeIdentifier: UTType.plainText.identifier, options: nil) { (item, error) in
                        if let text = item as? String {
                            let trimmedText = text.trimmingCharacters(in: .whitespacesAndNewlines)
                            if trimmedText.hasPrefix("http://") || trimmedText.hasPrefix("https://") {
                                completion(trimmedText)
                            } else if trimmedText.contains("://") {
                                completion(trimmedText)
                            } else if trimmedText.contains(".") && !trimmedText.contains(" ") && trimmedText.count > 4 {
                                completion("https://\(trimmedText)")
                            } else {
                                completion(nil)
                            }
                        } else {
                            completion(nil)
                        }
                    }
                    return
                }
            }
        }
        
        if let textContent = extensionItem.attributedContentText?.string {
            let trimmedText = textContent.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmedText.hasPrefix("http://") || trimmedText.hasPrefix("https://") {
                completion(trimmedText)
                return
            } else if trimmedText.contains("://") {
                completion(trimmedText)
                return
            }
        }
        
        completion(nil)
    }
    
    private func createJob(url: String) async {
        do {
            _ = try await apiService.createJob(videoURL: url)
            
            await MainActor.run {
                showSuccess("Started")
            }
            
            try? await Task.sleep(nanoseconds: UInt64(secondsBeforeAutoDismissAfterSuccess * 1_000_000_000))
            await MainActor.run {
                extensionContext?.completeRequest(returningItems: nil, completionHandler: nil)
            }
        } catch let error as APIError {
            await MainActor.run {
                showError("Failed: \(error.errorDescription ?? "Unknown error")")
            }
        } catch {
            await MainActor.run {
                showError("Failed: \(error.localizedDescription)")
            }
        }
    }
    
    private func showSuccess(_ message: String) {
        successImageView.isHidden = false
        statusLabel.text = message
        statusStackView.axis = .vertical
        statusStackView.spacing = 12
    }
    
    private func showError(_ message: String) {
        successImageView.isHidden = true
        statusLabel.text = message
        DispatchQueue.main.asyncAfter(deadline: .now() + 3.0) { [weak self] in
            self?.extensionContext?.completeRequest(returningItems: nil, completionHandler: nil)
        }
    }
}
