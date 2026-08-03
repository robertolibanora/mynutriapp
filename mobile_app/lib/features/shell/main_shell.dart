import 'package:flutter/material.dart';

import '../../widgets/empty_placeholder.dart';
import '../home/home_screen.dart';
import '../profile/profile_screen.dart';

class MainShell extends StatefulWidget {
  const MainShell({super.key});

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int _index = 0;

  static const _pages = <Widget>[
    HomeScreen(),
    _EmptyTab(
      title: 'Le mie diete',
      icon: Icons.restaurant_outlined,
      message: 'Nessuna dieta assegnata ancora',
    ),
    _EmptyTab(
      title: 'Appuntamenti',
      icon: Icons.event_busy_outlined,
      message: 'Nessun appuntamento',
    ),
    _EmptyTab(
      title: 'Progressi',
      icon: Icons.show_chart_outlined,
      message: 'Nessun progresso da mostrare ancora',
    ),
    ProfileScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(index: _index, children: _pages),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), label: 'Home'),
          NavigationDestination(
            icon: Icon(Icons.restaurant_outlined),
            label: 'Dieta',
          ),
          NavigationDestination(
            icon: Icon(Icons.calendar_month_outlined),
            label: 'Appuntamenti',
          ),
          NavigationDestination(
            icon: Icon(Icons.show_chart_outlined),
            label: 'Progressi',
          ),
          NavigationDestination(
            icon: Icon(Icons.person_outline),
            label: 'Profilo',
          ),
        ],
      ),
    );
  }
}

class _EmptyTab extends StatelessWidget {
  const _EmptyTab({
    required this.title,
    required this.icon,
    required this.message,
  });

  final String title;
  final IconData icon;
  final String message;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: EmptyPlaceholder(icon: icon, message: message),
    );
  }
}
