//
//  ContentView.swift
//  FactCheck
//
//  Created by harki bains on 12/30/25.
//

import SwiftUI
import PhotosUI
import UniformTypeIdentifiers
import Photos
import AuthenticationServices

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
    @StateObject private var authService = AuthService.shared
    @State private var selectedVideoItem: PhotosPickerItem? = nil
    @State private var selectedVideoData: Data? = nil
    @State private var selectedFailedJobId: String? = nil
    @State private var showURLInput: Bool = false
    @State private var urlInputText: String = ""
    @State private var showPhotoPicker: Bool = false
    
    var body: some View {
        Group {
            if authService.isAuthenticated {
                NavigationView {
                ScrollViewReader { proxy in
                List {
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
                        Text("Submit a video to get started")
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
                        .id(job.id)
                        .listRowInsets(EdgeInsets(top: 4, leading: 16, bottom: 4, trailing: 16))
                        .listRowSeparator(.hidden)
                    }
                    if viewModel.hasMoreJobs && !viewModel.jobs.isEmpty {
                        LoadMoreRow(
                            isLoadingMore: viewModel.isLoadingMore,
                            proxy: proxy,
                            anchorId: viewModel.jobs.last?.id,
                            onLoadMore: { await viewModel.loadMoreJobs() }
                        )
                        .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
                        .listRowSeparator(.hidden)
                    }
                }
            }
            .listStyle(PlainListStyle())
                }
            .refreshable {
                await viewModel.refreshJobs()
            }
            .navigationTitle("")
            .toolbar {
                // Settings menu (leading/left side)
                ToolbarItem(placement: .navigationBarLeading) {
                    Menu {
                        Button(role: .destructive, action: {
                            authService.signOut()
                        }) {
                            Label("Logout", systemImage: "arrow.right.square")
                        }
                    } label: {
                        Image(systemName: "gearshape")
                    }
                }
                
                // Plus button (trailing/right side)
                ToolbarItem(placement: .navigationBarTrailing) {
                    Menu {
                        Button(action: {
                            showURLInput = true
                        }) {
                            Label("URL", systemImage: "link")
                        }
                        
                        Button(action: {
                            showPhotoPicker = true
                        }) {
                            Label("Upload", systemImage: "photo")
                        }
                        .disabled(viewModel.isUploading || viewModel.isLoading)
                    } label: {
                        Image(systemName: "plus")
                    }
                }
            }
            .sheet(isPresented: $showURLInput) {
                URLInputSheet(
                    urlInputText: $urlInputText,
                    viewModel: viewModel,
                    isPresented: $showURLInput
                )
            }
            .sheet(isPresented: $showPhotoPicker) {
                PhotoPickerView(
                    selectedVideoItem: $selectedVideoItem,
                    isPresented: $showPhotoPicker
                )
            }
            .onChange(of: selectedVideoItem) { newItem in
                Task {
                    if let newItem = newItem {
                        if let data = try? await newItem.loadTransferable(type: Data.self) {
                            selectedVideoData = data
                            if let data = selectedVideoData {
                                viewModel.uploadVideo(videoData: data)
                                // Reset selection after upload
                                selectedVideoItem = nil
                                selectedVideoData = nil
                            }
                        }
                    }
                }
                }
            }
            } else {
                // Sign In Screen
                SignInView(authService: authService)
            }
        }
        .task {
            // Verify API key on app launch if one exists
            await authService.checkAuthenticationStatus()
        }
    }
}

// MARK: - Sign In View

struct SignInView: View {
    @ObservedObject var authService: AuthService
    
    var body: some View {
        VStack {
            Spacer()
            
            // Centered content
            VStack(spacing: 24) {
                // App Logo/Icon
                Image(systemName: "checkmark.shield.fill")
                    .font(.system(size: 80))
                    .foregroundColor(.blue)
                
                Text("FactCheck")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                
                Text("Verify the facts in your videos")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)
                
                if authService.isLoading {
                    VStack(spacing: 16) {
                        ProgressView()
                            .scaleEffect(1.5)
                        Text("Setting things up...")
                            .font(.body)
                            .foregroundColor(.secondary)
                    }
                    .padding(.top, 16)
                }
            }
            
            Spacer()
            
            // Sign In with Apple Button at bottom
            Button(action: {
                authService.signInWithApple()
            }) {
                HStack {
                    Image(systemName: "applelogo")
                        .font(.system(size: 18))
                    Text("Sign in with Apple")
                        .font(.headline)
                }
                .foregroundColor(.white)
                .frame(maxWidth: .infinity)
                .frame(height: 50)
                .background(authService.isLoading ? Color.gray : Color.black)
                .cornerRadius(10)
            }
            .padding(.horizontal, 40)
            .padding(.bottom, 40)
            .disabled(authService.isLoading)
        }
    }
}

// MARK: - URL Input Sheet

struct URLInputSheet: View {
    @Binding var urlInputText: String
    @ObservedObject var viewModel: FactCheckViewModel
    @Binding var isPresented: Bool
    @FocusState private var isTextFieldFocused: Bool
    
    var body: some View {
        NavigationView {
            VStack(spacing: 20) {
                TextField("Enter video URL", text: $urlInputText)
                    .textFieldStyle(RoundedBorderTextFieldStyle())
                    .autocapitalization(.none)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
                    .focused($isTextFieldFocused)
                    .padding()
                
                Button(action: {
                    guard !urlInputText.isEmpty else {
                        return
                    }
                    
                    // Validate URL format
                    guard URL(string: urlInputText.trimmingCharacters(in: .whitespacesAndNewlines)) != nil else {
                        viewModel.errorMessage = "Please enter a valid URL"
                        return
                    }
                    
                    // Set the URL and submit
                    viewModel.videoURL = urlInputText.trimmingCharacters(in: .whitespacesAndNewlines)
                    viewModel.submitJob()
                    
                    // Clear input and dismiss
                    urlInputText = ""
                    isPresented = false
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
                    .background(viewModel.isLoading || urlInputText.isEmpty ? Color.gray : Color.blue)
                    .foregroundColor(.white)
                    .cornerRadius(10)
                }
                .disabled(viewModel.isLoading || urlInputText.isEmpty || viewModel.isUploading)
                .padding(.horizontal)
                
                Spacer()
            }
            .navigationTitle("Enter Video URL")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") {
                        urlInputText = ""
                        isPresented = false
                    }
                }
            }
            .onAppear {
                isTextFieldFocused = true
            }
        }
    }
}

// MARK: - Photo Picker View

struct PhotoPickerView: View {
    @Binding var selectedVideoItem: PhotosPickerItem?
    @Binding var isPresented: Bool
    
    var body: some View {
        NavigationView {
            VStack(spacing: 20) {
                PhotosPicker(
                    selection: Binding(
                        get: { selectedVideoItem },
                        set: { newValue in
                            selectedVideoItem = newValue
                            if newValue != nil {
                                isPresented = false
                            }
                        }
                    ),
                    matching: .videos,
                    photoLibrary: .shared()
                ) {
                    Label("Choose Video", systemImage: "photo.on.rectangle")
                        .font(.headline)
                        .foregroundColor(.white)
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color.blue)
                        .cornerRadius(10)
                }
                .padding()
                
                Spacer()
            }
            .navigationTitle("Select Video")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") {
                        isPresented = false
                    }
                }
            }
        }
    }
}

// MARK: - Load More Row

struct LoadMoreRow: View {
    let isLoadingMore: Bool
    let proxy: ScrollViewProxy
    let anchorId: String?
    let onLoadMore: () async -> Void
    
    @State private var dragOffset: CGFloat = 0
    private let triggerThreshold: CGFloat = 50
    
    var body: some View {
        HStack {
            Spacer()
            Group {
                if isLoadingMore {
                    ProgressView()
                        .scaleEffect(1.4)
                } else {
                    Image(systemName: "chevron.down")
                        .font(.system(size: 28, weight: .medium))
                        .foregroundColor(.secondary)
                        .scaleEffect(1 + min(dragOffset / triggerThreshold * 0.3, 0.3))
                }
            }
            .padding(.vertical, 16)
            .frame(maxWidth: .infinity)
            .contentShape(Rectangle())
            .simultaneousGesture(
                DragGesture(minimumDistance: 15)
                    .onChanged { value in
                        if !isLoadingMore, value.translation.height < 0 {
                            dragOffset = -value.translation.height
                        }
                    }
                    .onEnded { value in
                        if !isLoadingMore, value.translation.height < -triggerThreshold {
                            let anchor = anchorId
                            Task {
                                await onLoadMore()
                                if let id = anchor {
                                    try? await Task.sleep(nanoseconds: 50_000_000)
                                    await MainActor.run {
                                        withAnimation(.easeOut(duration: 0.15)) {
                                            proxy.scrollTo(id, anchor: .bottom)
                                        }
                                    }
                                }
                            }
                        }
                        dragOffset = 0
                    }
            )
            Spacer()
        }
    }
}

// MARK: - Job Card View

struct JobCardView: View {
    let job: JobResponse
    let isExpanded: Bool
    let viewModel: FactCheckViewModel
    let onTap: () -> Void
    
    @Environment(\.colorScheme) private var colorScheme
    @State private var thumbnailURL: URL?
    @State private var cachedThumbnail: UIImage?
    @State private var isLoadingThumbnail = false
    @State private var isFailedDownloadSectionExpanded = false
    
    private func loadThumbnail() {
        // Only load if we don't have a cached thumbnail or URL, not already loading, and job has frames
        guard cachedThumbnail == nil, thumbnailURL == nil, !isLoadingThumbnail, job.frames_s3_prefix != nil else {
            return
        }
        
        // Check job_id-based cache first
        if let cachedImage = ThumbnailCacheManager.shared.getCachedThumbnail(jobId: job.id) {
            cachedThumbnail = cachedImage
            return
        }
        
        // If not cached, fetch presigned URL
        isLoadingThumbnail = true
        Task {
            do {
                let url = try await APIService.shared.getThumbnailURL(jobId: job.id)
                await MainActor.run {
                    thumbnailURL = url
                    isLoadingThumbnail = false
                }
            } catch {
                await MainActor.run {
                    isLoadingThumbnail = false
                }
            }
        }
    }
    
    /// Preload thumbnail image into cache for faster subsequent loads
    private func preloadThumbnail(url: URL) async {
        // Check if already cached by job_id
        if ThumbnailCacheManager.shared.hasCachedThumbnail(jobId: job.id) {
            return // Already cached
        }
        
        // Load and cache the image
        do {
            let (data, response) = try await URLSession.shared.data(for: URLRequest(url: url))
            if let httpResponse = response as? HTTPURLResponse,
               (200...299).contains(httpResponse.statusCode),
               let image = UIImage(data: data) {
                // Store in job_id-based cache
                ThumbnailCacheManager.shared.storeThumbnail(jobId: job.id, image: image)
                
                // Update UI with cached image
                await MainActor.run {
                    cachedThumbnail = image
                }
            }
        } catch {
            // Silently fail - AsyncImage will handle loading
        }
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Collapsed Header
            HStack(spacing: 12) {
                // First frame thumbnail
                let thumbHeight: CGFloat = 70
                let thumbWidth: CGFloat = thumbHeight * (9.0/16.0)
                if let cachedImage = cachedThumbnail {
                    // Use cached image directly
                    Image(uiImage: cachedImage)
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                        .frame(width: thumbWidth, height: thumbHeight)
                        .clipped()
                        .cornerRadius(8)
                } else if let url = thumbnailURL {
                    AsyncImage(url: url) { phase in
                        switch phase {
                        case .empty:
                            ProgressView()
                                .frame(width: thumbWidth, height: thumbHeight)
                        case .success(let image):
                            image
                                .resizable()
                                .aspectRatio(contentMode: .fill)
                                .frame(width: thumbWidth, height: thumbHeight)
                                .clipped()
                                .cornerRadius(8)
                        case .failure:
                            Image(systemName: "photo")
                                .foregroundColor(.secondary)
                                .frame(width: thumbWidth, height: thumbHeight)
                                .background(Color(.secondarySystemBackground))
                                .cornerRadius(8)
                        @unknown default:
                            EmptyView()
                        }
                    }
                    .task {
                        // Preload image into job_id cache if not already cached
                        await preloadThumbnail(url: url)
                    }
                } else if isLoadingThumbnail {
                    ProgressView()
                        .frame(width: thumbWidth, height: thumbHeight)
                } else {
                    // Placeholder when no frame available
                    Image(systemName: "photo")
                        .foregroundColor(.secondary)
                        .frame(width: thumbWidth, height: thumbHeight)
                        .background(Color(.secondarySystemBackground))
                        .cornerRadius(8)
                }
                
                VStack(alignment: .leading, spacing: 4) {
                    Text(job.title ?? "Untitled")
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .lineLimit(3)
                        .fixedSize(horizontal: false, vertical: true)
                    
                    HStack(spacing: 8) {
                        // Status Badge (only show if not completed)
                        if job.status != "completed" {
                            StatusBadge(status: job.failed == true ? "failed_\(job.status)" : job.status)
                        }
                        
                        // Verdict Summary Badges (if completed) - show summation of all verdicts
                        if job.status == "completed", let verifiedClaims = job.verified_claims, !verifiedClaims.verifications.isEmpty {
                            VerdictSummaryBadges(verifications: verifiedClaims.verifications)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                
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
            .task(id: "\(job.id)-\(job.status)") {
                loadThumbnail()
            }
            
            // Direct Upload Section for failed downloading jobs (collapsible)
            if job.status == "downloading" && job.failed == true {
                Divider()
                    .padding(.vertical, 2)
                
                VStack(alignment: .leading, spacing: 0) {
                    // Collapsible Header
                    Button(action: {
                        isFailedDownloadSectionExpanded.toggle()
                    }) {
                        HStack {
                            Text("Try direct video upload")
                                .font(.subheadline)
                                .fontWeight(.medium)
                                .foregroundColor(.primary)
                            Spacer()
                            Image(systemName: isFailedDownloadSectionExpanded ? "chevron.up" : "chevron.down")
                                .foregroundColor(.secondary)
                                .font(.caption)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.vertical, 2)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(PlainButtonStyle())
                    
                    // Collapsible Content
                    if isFailedDownloadSectionExpanded {
                        VStack(alignment: .leading, spacing: 12) {
                            // Upload video text
                            Text("Download or screen record video to camera roll")
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                                .allowsHitTesting(false)

                            // Open Media Button
                            if let url = URL(string: job.video_url) {
                                Button(action: {
                                    UIApplication.shared.open(url)
                                }) {
                                    HStack {
                                        Image(systemName: "safari")
                                        Text("Open Media")
                                    }
                                    .frame(maxWidth: .infinity)
                                    .padding()
                                    .background(Color.blue)
                                    .foregroundColor(.white)
                                    .cornerRadius(10)
                                }
                                .buttonStyle(PlainButtonStyle())
                            }
                            
                            // Upload video text
                            Text("Upload video")
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                                .allowsHitTesting(false)
                            
                            // Upload video button
                            PhotosPicker(
                                selection: Binding(
                                    get: { nil },
                                    set: { newItem in
                                        if let newItem = newItem {
                                            Task {
                                                if let data = try? await newItem.loadTransferable(type: Data.self) {
                                                    viewModel.uploadVideoForFailedJob(jobId: job.id, videoData: data)
                                                }
                                            }
                                        }
                                    }
                                ),
                                matching: .videos,
                                photoLibrary: .shared()
                            ) {
                                HStack {
                                    Image(systemName: "arrow.up.circle.fill")
                                    Text("Upload Video")
                                }
                                .frame(maxWidth: .infinity)
                                .padding()
                                .background(viewModel.isUploading || viewModel.isLoading ? Color.gray : Color.orange)
                                .foregroundColor(.white)
                                .cornerRadius(10)
                            }
                            .buttonStyle(PlainButtonStyle())
                            .disabled(viewModel.isUploading || viewModel.isLoading)
                        }
                        .padding(.top, 8)
                    }
                }
            }
            
            // Expanded Content (only if completed and expanded)
            if job.status == "completed" && isExpanded {
                Divider()
                
                if let verifiedClaims = job.verified_claims {
                    // Verifications Section (replaces claims + claim_results)
                    if !verifiedClaims.verifications.isEmpty {
                        VStack(alignment: .leading, spacing: 12) {
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
                            Text("Open Media")
                        }
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color.blue)
                        .foregroundColor(.white)
                        .cornerRadius(10)
                    }
                    .buttonStyle(PlainButtonStyle())
                    .padding(.top, 8)
                }
            }
        }
        .padding()
        .background(colorScheme == .dark ? Color(.secondarySystemBackground) : Color(.systemBackground))
        .cornerRadius(12)
        .shadow(color: Color.black.opacity(colorScheme == .dark ? 0.3 : 0.1), radius: 4, x: 0, y: 2)
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
                            .fixedSize(horizontal: false, vertical: true)
                            .multilineTextAlignment(.leading)
                    }
                    
                    HStack {
                        VerdictBadge(verdict: verification.verdict)
                        Spacer()
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                
                Spacer()
                
                // Expand/Collapse Indicator
                Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                    .foregroundColor(.secondary)
                    .font(.caption)
            }
            .layoutPriority(1)
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
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color(.separator), lineWidth: 1)
        )
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
                
                // Citation text (from [text](url)) on the right
                Text(citation.originalText)
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
        let lowercasedStatus = status.lowercased()
        if lowercasedStatus.hasPrefix("failed") {
            return .red
        }
        switch lowercasedStatus {
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
        HStack(spacing: 4) {
            Image(systemName: verdictIcon(for: verdict))
                .font(.caption2)
            Text(verdictDisplayText(for: verdict))
                .font(.caption)
                .fontWeight(.semibold)
        }
        .foregroundColor(.white)
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(verdictColor(for: verdict))
        .cornerRadius(6)
    }
    
    private func verdictColor(for verdict: String) -> Color {
        switch verdict.uppercased() {
        case "TRUE", "SUPPORTED":
            return .green
        case "FALSE", "NOT_SUPPORTED":
            return .red
        case "PARTIALLY_TRUE", "PARTIALLY_SUPPORTED":
            return .orange
        case "MISLEADING":
            return .orange
        case "UNVERIFIABLE", "DISPUTED":
            return .yellow
        case "NOT_FACTUAL":
            return .gray
        default:
            return .primary
        }
    }
    
    private func verdictIcon(for verdict: String) -> String {
        switch verdict.uppercased() {
        case "TRUE", "SUPPORTED":
            return "checkmark.circle.fill"
        case "FALSE", "NOT_SUPPORTED":
            return "xmark.circle.fill"
        case "PARTIALLY_TRUE", "PARTIALLY_SUPPORTED":
            return "exclamationmark.circle.fill"
        case "MISLEADING":
            return "exclamationmark.triangle.fill"
        case "UNVERIFIABLE", "DISPUTED":
            return "questionmark.circle.fill"
        case "NOT_FACTUAL":
            return "minus.circle.fill"
        default:
            return "circle.fill"
        }
    }
    
    private func verdictDisplayText(for verdict: String) -> String {
        switch verdict.uppercased() {
        case "TRUE":
            return "True"
        case "SUPPORTED":
            return "Supported"
        case "FALSE":
            return "False"
        case "NOT_SUPPORTED":
            return "Not Supported"
        case "PARTIALLY_TRUE":
            return "Partially True"
        case "PARTIALLY_SUPPORTED":
            return "Partially Supported"
        case "MISLEADING":
            return "Misleading"
        case "UNVERIFIABLE":
            return "Unverifiable"
        case "DISPUTED":
            return "Disputed"
        case "NOT_FACTUAL":
            return "Not Factual"
        default:
            return verdict.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }
}

// MARK: - Verdict Summary Badges

struct VerdictSummaryBadges: View {
    let verifications: [Verification]
    
    private var verdictCounts: [String: Int] {
        Dictionary(grouping: verifications, by: { $0.verdict })
            .mapValues { $0.count }
    }
    
    private var summaryVerdict: String {
        // Count verdicts (support both old and new terms)
        let supportedCount = (verdictCounts["TRUE"] ?? 0) + (verdictCounts["SUPPORTED"] ?? 0)
        let partiallySupportedCount = (verdictCounts["PARTIALLY_TRUE"] ?? 0) + (verdictCounts["PARTIALLY_SUPPORTED"] ?? 0)
        let misleadingCount = verdictCounts["MISLEADING"] ?? 0
        
        // Calculate numerator = (# supported) + (# partially supported)/2 + (# misleading)*0.25
        let numerator = Double(supportedCount) + Double(partiallySupportedCount) / 2.0 + Double(misleadingCount) * 0.25
        
        // Calculate denominator = number of verdicts
        let denominator = Double(verifications.count)
        
        // Handle divide by zero case
        guard denominator > 0 else {
            // Return most common verdict
            return mostCommonVerdict()
        }
        
        // Calculate score = numerator / denominator
        let score = numerator / denominator
        
        // Determine summary verdict based on score (use new terms for output)
        if score == 1.0 {
            if partiallySupportedCount > 0 || misleadingCount > 0 {
                return "MOSTLY_SUPPORTED"
            } else {
                return "SUPPORTED"
            }
        } else if score > 0.65 {
            return "MOSTLY_SUPPORTED"
        } else if score > 0.45 {
            return "PARTIALLY_SUPPORTED"
        } else {
            return "NOT_SUPPORTED"
        }
    }
    
    private func mostCommonVerdict() -> String {
        guard let maxVerdict = verdictCounts.max(by: { $0.value < $1.value }) else {
            return "UNVERIFIABLE"
        }
        return maxVerdict.key
    }
    
    private func verdictColor(for verdict: String) -> Color {
        switch verdict.uppercased() {
        case "TRUE", "SUPPORTED":
            return .green
        case "MOSTLY_TRUE", "MOSTLY_SUPPORTED":
            return .green.opacity(0.8)
        case "FALSE", "NOT_SUPPORTED", "NOT_TRUE":
            return .red
        case "PARTIALLY_TRUE", "PARTIALLY_SUPPORTED":
            return .orange
        case "MISLEADING":
            return .orange
        case "UNVERIFIABLE", "DISPUTED":
            return .yellow
        case "NOT_FACTUAL":
            return .gray
        default:
            return .primary
        }
    }
    
    private func verdictIcon(for verdict: String) -> String {
        switch verdict.uppercased() {
        case "TRUE", "SUPPORTED", "MOSTLY_TRUE", "MOSTLY_SUPPORTED":
            return "checkmark.circle.fill"
        case "FALSE", "NOT_SUPPORTED", "NOT_TRUE":
            return "xmark.circle.fill"
        case "PARTIALLY_TRUE", "PARTIALLY_SUPPORTED":
            return "exclamationmark.circle.fill"
        case "MISLEADING":
            return "exclamationmark.triangle.fill"
        case "UNVERIFIABLE", "DISPUTED":
            return "questionmark.circle.fill"
        case "NOT_FACTUAL":
            return "minus.circle.fill"
        default:
            return "circle.fill"
        }
    }
    
    private func verdictDisplayText(for verdict: String) -> String {
        switch verdict.uppercased() {
        case "TRUE":
            return "True"
        case "SUPPORTED":
            return "Supported"
        case "MOSTLY_TRUE":
            return "Mostly True"
        case "MOSTLY_SUPPORTED":
            return "Mostly Supported"
        case "FALSE":
            return "False"
        case "NOT_SUPPORTED", "NOT_TRUE":
            return "Not Supported"
        case "PARTIALLY_TRUE":
            return "Partially True"
        case "PARTIALLY_SUPPORTED":
            return "Partially Supported"
        case "MISLEADING":
            return "Misleading"
        case "UNVERIFIABLE":
            return "Unverifiable"
        case "DISPUTED":
            return "Disputed"
        case "NOT_FACTUAL":
            return "Not Factual"
        default:
            return verdict.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }
    
    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: verdictIcon(for: summaryVerdict))
                .font(.caption2)
            Text(verdictDisplayText(for: summaryVerdict))
                .font(.caption)
                .fontWeight(.semibold)
        }
        .foregroundColor(.white)
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(verdictColor(for: summaryVerdict))
        .cornerRadius(6)
    }
}

#Preview {
    ContentView()
        .environmentObject(FactCheckViewModel())
}
