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
            ContentView()
                .tint(ReSpaceStyle.purple)
                .font(ReSpaceStyle.font())
                .preferredColorScheme(.light)
        }
    }
}
