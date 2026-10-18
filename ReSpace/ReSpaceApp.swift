//
//  ReSpaceApp.swift
//  ReSpace
//
//  Created by Kenshu Dieguez on 10/17/26.
//

import SwiftUI

@main
struct ReSpaceApp: App {
    init() { ReSpaceStyle.registerFonts() }

    var body: some Scene {
        WindowGroup {
            Group {
                #if DEBUG
                if ProcessInfo.processInfo.arguments.contains("--ui-demo") { UIDemoGallery() }
                else { ContentView() }
                #else
                ContentView()
                #endif
            }
                .tint(ReSpaceStyle.purple)
                .font(ReSpaceStyle.font())
                .preferredColorScheme(.light)
        }
    }
}
