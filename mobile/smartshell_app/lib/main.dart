import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';

void main() {
  runApp(const SmartShellApp());
}

const serviceUuid = 'f2d00001-8b6b-4d5d-9d53-5e77295c1c01';
const rxUuid = 'f2d00002-8b6b-4d5d-9d53-5e77295c1c01';
const txUuid = 'f2d00003-8b6b-4d5d-9d53-5e77295c1c01';

class EmergencyContact {
  EmergencyContact({
    required this.name,
    required this.phone,
    required this.priority,
  });

  final String name;
  final String phone;
  final int priority;

  factory EmergencyContact.fromJson(Map<String, dynamic> json) {
    return EmergencyContact(
      name: '${json['name'] ?? ''}',
      phone: '${json['phone'] ?? ''}',
      priority: int.tryParse('${json['priority'] ?? 0}') ?? 0,
    );
  }

  Map<String, dynamic> toJson() {
    return {'name': name, 'phone': phone, 'priority': priority};
  }
}

class HelmetConfig {
  HelmetConfig({
    required this.riderName,
    required this.homeBarangay,
    required this.contacts,
    required this.messageTemplate,
  });

  final String riderName;
  final String homeBarangay;
  final List<EmergencyContact> contacts;
  final String messageTemplate;

  factory HelmetConfig.fromJson(Map<String, dynamic> json) {
    final rawContacts = json['contacts'];
    return HelmetConfig(
      riderName: '${json['rider_name'] ?? ''}',
      homeBarangay: '${json['subject_home_barangay'] ?? ''}',
      contacts:
          rawContacts is List
              ? rawContacts
                  .whereType<Map>()
                  .map((e) => EmergencyContact.fromJson(e.cast()))
                  .toList()
              : <EmergencyContact>[],
      messageTemplate: '${json['message_template'] ?? ''}',
    );
  }
}

class ConfigResponse {
  ConfigResponse(this.raw);

  final Map<String, dynamic> raw;

  bool get ok => raw['ok'] == true;
  String get error => '${raw['error'] ?? 'Unknown error'}';

  HelmetConfig? get config {
    final data = raw['data'];
    if (data is Map<String, dynamic> && data.containsKey('contacts')) {
      return HelmetConfig.fromJson(data);
    }
    return null;
  }
}

abstract class ConfigTransport {
  String get label;
  Future<ConfigResponse> send(Map<String, dynamic> command);
  Future<void> close() async {}
}

class MockConfigTransport implements ConfigTransport {
  MockConfigTransport();

  String _mockPin = '000000';

  HelmetConfig _config = HelmetConfig(
    riderName: 'Juan Dela Cruz',
    homeBarangay: 'Zapote',
    contacts: [
      EmergencyContact(name: 'JM', phone: '+639202828660', priority: 1),
      EmergencyContact(name: 'Juls', phone: '+639278222260', priority: 2),
      EmergencyContact(name: 'Jom', phone: '+639922547260', priority: 3),
    ],
    messageTemplate:
        'SMARTSHELL COLLISION ALERT\n\n'
        'Rider: {name}\n'
        'Home: {home_barangay}\n'
        'Accident: {accident_barangay}\n\n'
        'GPS: {map_url}',
  );

  @override
  String get label => 'Mock helmet';

  @override
  Future<void> close() async {}

  @override
  Future<ConfigResponse> send(Map<String, dynamic> command) async {
    await Future<void>.delayed(const Duration(milliseconds: 250));
    final op = '${command['op'] ?? ''}'.toLowerCase();
    if (op == 'ping' || op == 'status') {
      return ConfigResponse({
        'ok': true,
        'data': {'service': 'SmartShell Config', 'auth_required': true},
      });
    }
    if ('${command['pin'] ?? ''}' != _mockPin) {
      return ConfigResponse({
        'ok': false,
        'auth_required': true,
        'error': 'invalid or missing config PIN',
      });
    }

    switch (op) {
      case 'get_config':
      case 'get':
      case 'read_config':
        return ConfigResponse({'ok': true, 'data': _toProtocolJson()});
      case 'set_rider':
        _config = HelmetConfig(
          riderName: '${command['rider_name'] ?? _config.riderName}'.trim(),
          homeBarangay:
              '${command['subject_home_barangay'] ?? command['home'] ?? _config.homeBarangay}'
                  .trim(),
          contacts: _config.contacts,
          messageTemplate: _config.messageTemplate,
        );
        return ConfigResponse({'ok': true, 'data': _toProtocolJson()});
      case 'change_pin':
        final newPin = '${command['new_pin'] ?? ''}'.trim();
        if (!_validPin(newPin)) {
          return ConfigResponse({
            'ok': false,
            'error': 'PIN must be 4-12 digits',
          });
        }
        _mockPin = newPin;
        return ConfigResponse({
          'ok': true,
          'data': {'pin_changed': true},
        });
      case 'add_contact':
        if (_config.contacts.length >= 3) {
          return ConfigResponse({
            'ok': false,
            'error': 'Contact limit reached (3)',
          });
        }
        _config = _withContacts([
          ..._config.contacts,
          EmergencyContact(
            name: '${command['name'] ?? ''}'.trim(),
            phone: '${command['phone'] ?? ''}'.trim(),
            priority: _config.contacts.length + 1,
          ),
        ]);
        return ConfigResponse({'ok': true, 'data': _toProtocolJson()});
      case 'update_contact':
        final index = int.tryParse('${command['index'] ?? ''}') ?? 0;
        if (index < 1 || index > _config.contacts.length) {
          return ConfigResponse({
            'ok': false,
            'error': 'Contact index out of range',
          });
        }
        final contacts = [..._config.contacts];
        final old = contacts[index - 1];
        contacts[index - 1] = EmergencyContact(
          name: '${command['name'] ?? old.name}'.trim(),
          phone: '${command['phone'] ?? old.phone}'.trim(),
          priority: old.priority,
        );
        _config = _withContacts(contacts);
        return ConfigResponse({'ok': true, 'data': _toProtocolJson()});
      case 'delete_contact':
        final index = int.tryParse('${command['index'] ?? ''}') ?? 0;
        if (index < 1 || index > _config.contacts.length) {
          return ConfigResponse({
            'ok': false,
            'error': 'Contact index out of range',
          });
        }
        final contacts = [..._config.contacts]..removeAt(index - 1);
        _config = _withContacts(contacts);
        return ConfigResponse({'ok': true, 'data': _toProtocolJson()});
      default:
        return ConfigResponse({'ok': false, 'error': 'Unsupported op: $op'});
    }
  }

  HelmetConfig _withContacts(List<EmergencyContact> contacts) {
    final normalized = <EmergencyContact>[];
    for (var i = 0; i < contacts.length; i++) {
      normalized.add(
        EmergencyContact(
          name: contacts[i].name,
          phone: contacts[i].phone,
          priority: i + 1,
        ),
      );
    }
    return HelmetConfig(
      riderName: _config.riderName,
      homeBarangay: _config.homeBarangay,
      contacts: normalized,
      messageTemplate: _config.messageTemplate,
    );
  }

  Map<String, dynamic> _toProtocolJson() {
    return {
      'rider_name': _config.riderName,
      'subject_home_barangay': _config.homeBarangay,
      'contacts': _config.contacts.map((c) => c.toJson()).toList(),
      'message_template': _config.messageTemplate,
    };
  }

  bool _validPin(String value) {
    final re = RegExp(r'^\d{4,12}$');
    return re.hasMatch(value);
  }
}

class BleConfigTransport implements ConfigTransport {
  BleConfigTransport({
    required this.device,
    required this.rx,
    required this.tx,
  });

  final BluetoothDevice device;
  final BluetoothCharacteristic rx;
  final BluetoothCharacteristic tx;

  static Future<BleConfigTransport> connectFirst({
    Duration scanTimeout = const Duration(seconds: 8),
  }) async {
    final results = await scanSmartShell(scanTimeout: scanTimeout);
    if (results.isEmpty) {
      throw Exception('No SmartShell BLE device found.');
    }
    return connectTo(results.first);
  }

  static Future<List<ScanResult>> scanSmartShell({
    Duration scanTimeout = const Duration(seconds: 8),
  }) async {
    if (await FlutterBluePlus.isSupported == false) {
      throw Exception('Bluetooth is not supported on this device.');
    }

    final serviceGuid = Guid(serviceUuid);
    final results = <ScanResult>[];
    late StreamSubscription<List<ScanResult>> scanSub;

    scanSub = FlutterBluePlus.scanResults.listen((items) {
      for (final item in items) {
        final alreadyKnown = results.any(
          (r) => r.device.remoteId == item.device.remoteId,
        );
        if (!alreadyKnown) {
          results.add(item);
        }
      }
    });

    await FlutterBluePlus.startScan(
      withServices: [serviceGuid],
      timeout: scanTimeout,
    );
    await Future<void>.delayed(scanTimeout);
    await FlutterBluePlus.stopScan();
    await scanSub.cancel();

    return results.where((r) {
      final name =
          r.device.platformName.isNotEmpty
              ? r.device.platformName
              : r.advertisementData.advName;
      return name.toLowerCase().contains('smartshell') ||
          r.advertisementData.serviceUuids.contains(serviceGuid);
    }).toList();
  }

  static Future<BleConfigTransport> connectTo(ScanResult result) async {
    final serviceGuid = Guid(serviceUuid);
    final rxGuid = Guid(rxUuid);
    final txGuid = Guid(txUuid);
    final device = result.device;
    await device.connect(
      license: License.free,
      timeout: const Duration(seconds: 15),
    );
    final services = await device.discoverServices();
    final service = services.firstWhere(
      (s) => s.uuid == serviceGuid,
      orElse: () => throw Exception('SmartShell config service not found.'),
    );
    final rx = service.characteristics.firstWhere(
      (c) => c.uuid == rxGuid,
      orElse: () => throw Exception('SmartShell RX characteristic not found.'),
    );
    final tx = service.characteristics.firstWhere(
      (c) => c.uuid == txGuid,
      orElse: () => throw Exception('SmartShell TX characteristic not found.'),
    );
    await tx.setNotifyValue(true);
    return BleConfigTransport(device: device, rx: rx, tx: tx);
  }

  static String displayName(ScanResult result) {
    final name =
        result.device.platformName.isNotEmpty
            ? result.device.platformName
            : result.advertisementData.advName;
    return name.isEmpty ? 'SmartShell (${result.device.remoteId})' : name;
  }

  static bool sameDevice(ScanResult a, ScanResult b) {
    return a.device.remoteId == b.device.remoteId;
  }

  @override
  String get label {
    final name = device.platformName;
    return name.isEmpty ? 'BLE SmartShell' : name;
  }

  @override
  Future<void> close() async {
    try {
      await device.disconnect();
    } catch (_) {
      // Device may already be disconnected.
    }
  }

  @override
  Future<ConfigResponse> send(Map<String, dynamic> command) async {
    final completer = Completer<ConfigResponse>();
    final buffer = BytesBuilder();
    late StreamSubscription<List<int>> sub;

    sub = tx.onValueReceived.listen((chunk) async {
      buffer.add(chunk);
      final bytes = buffer.toBytes();
      final newline = bytes.indexOf(10);
      if (newline < 0 || completer.isCompleted) {
        return;
      }
      await sub.cancel();
      final line = utf8.decode(bytes.sublist(0, newline));
      completer.complete(
        ConfigResponse(jsonDecode(line) as Map<String, dynamic>),
      );
    });

    final payload = '${jsonEncode(command)}\n';
    await rx.write(utf8.encode(payload), withoutResponse: false);
    return completer.future.timeout(
      const Duration(seconds: 10),
      onTimeout: () async {
        await sub.cancel();
        return ConfigResponse({
          'ok': false,
          'error': 'Timed out waiting for BLE response',
        });
      },
    );
  }
}

class SmartShellApp extends StatelessWidget {
  const SmartShellApp({super.key});

  @override
  Widget build(BuildContext context) {
    final scheme = ColorScheme.fromSeed(
      seedColor: const Color(0xff3b82f6),
      brightness: Brightness.dark,
    );
    return MaterialApp(
      title: 'SmartShell',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: scheme,
        scaffoldBackgroundColor: const Color(0xff101114),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: Colors.black.withValues(alpha: 0.25),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(14)),
        ),
      ),
      home: const ConnectScreen(),
    );
  }
}

class ConnectScreen extends StatefulWidget {
  const ConnectScreen({super.key});

  @override
  State<ConnectScreen> createState() => _ConnectScreenState();
}

class _ConnectScreenState extends State<ConnectScreen> {
  final _pinController = TextEditingController();
  bool _loading = false;
  bool _scanning = false;
  List<ScanResult> _helmets = [];
  ScanResult? _selectedHelmet;
  String _status = 'Scan for nearby SmartShell helmets, then enter the PIN.';

  @override
  void dispose() {
    _pinController.dispose();
    super.dispose();
  }

  Future<void> _connect() async {
    final pin = _pinController.text.trim();
    if (pin.isEmpty) {
      setState(() {
        _status = 'Enter the helmet PIN before connecting.';
      });
      return;
    }

    setState(() {
      _loading = true;
      _status = 'Connecting...';
    });

    late final ConfigTransport transport;
    try {
      final ScanResult selected;
      if (_selectedHelmet != null) {
        selected = _selectedHelmet!;
      } else {
        final results = await BleConfigTransport.scanSmartShell();
        if (results.isEmpty) {
          throw Exception('No SmartShell helmets found.');
        }
        selected = results.first;
      }
      transport = await BleConfigTransport.connectTo(selected);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _status = '$e';
      });
      return;
    }
    final ping = await transport.send({'op': 'ping'});
    if (!mounted) return;
    if (!ping.ok) {
      await transport.close();
      setState(() {
        _loading = false;
        _status = ping.error;
      });
      return;
    }

    final response = await transport.send({'op': 'get_config', 'pin': pin});
    if (!mounted) return;
    if (!response.ok || response.config == null) {
      await transport.close();
      setState(() {
        _loading = false;
        _status = response.error;
      });
      return;
    }

    Navigator.of(context).pushReplacement(
      MaterialPageRoute<void>(
        builder:
            (_) => ConfigHomeScreen(
              transport: transport,
              initialConfig: response.config!,
              pin: pin,
            ),
      ),
    );
  }

  Future<void> _scanHelmets() async {
    setState(() {
      _scanning = true;
      _status = 'Scanning for SmartShell helmets...';
      _helmets = [];
      _selectedHelmet = null;
    });
    try {
      final results = await BleConfigTransport.scanSmartShell();
      if (!mounted) return;
      setState(() {
        _helmets = results;
        _selectedHelmet = results.isEmpty ? null : results.first;
        _status =
            results.isEmpty
                ? 'No SmartShell helmets found. Make sure the Pi BLE server is running.'
                : 'Found ${results.length} helmet(s). Select one, then connect.';
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _status = '$e';
      });
    } finally {
      if (mounted) {
        setState(() {
          _scanning = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 460),
              child: GlassCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Icon(
                      Icons.sports_motorsports,
                      size: 52,
                      color: Color(0xff60a5fa),
                    ),
                    const SizedBox(height: 16),
                    Text(
                      'SmartShell Link',
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.headlineMedium
                          ?.copyWith(fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Manage rider info and emergency contacts over local Bluetooth.',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.68),
                      ),
                    ),
                    const SizedBox(height: 24),
                    OutlinedButton.icon(
                      onPressed: _scanning || _loading ? null : _scanHelmets,
                      icon:
                          _scanning
                              ? const SizedBox(
                                width: 18,
                                height: 18,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                              : const Icon(Icons.search),
                      label: const Text('Scan for Helmets'),
                    ),
                    const SizedBox(height: 12),
                    if (_helmets.isNotEmpty)
                      ..._helmets.map(
                        (helmet) => RadioListTile<ScanResult>(
                          value: helmet,
                          groupValue: _selectedHelmet,
                          onChanged:
                              _loading || _scanning
                                  ? null
                                  : (value) =>
                                      setState(() => _selectedHelmet = value),
                          title: Text(BleConfigTransport.displayName(helmet)),
                          subtitle: Text(
                            '${helmet.device.remoteId} • RSSI ${helmet.rssi}',
                          ),
                        ),
                      ),
                    const SizedBox(height: 8),
                    TextField(
                      controller: _pinController,
                      decoration: const InputDecoration(
                        labelText: 'Helmet PIN',
                        helperText: 'Enter the current helmet config PIN.',
                        prefixIcon: Icon(Icons.lock_outline),
                      ),
                      obscureText: true,
                      keyboardType: TextInputType.number,
                    ),
                    const SizedBox(height: 16),
                    FilledButton.icon(
                      onPressed: _loading ? null : _connect,
                      icon:
                          _loading
                              ? const SizedBox(
                                width: 18,
                                height: 18,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                              : const Icon(Icons.bluetooth_connected),
                      label: const Text('Connect to Helmet'),
                    ),
                    const SizedBox(height: 12),
                    Text(_status, textAlign: TextAlign.center),
                    const SizedBox(height: 20),
                    const ProtocolCard(),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class ConfigHomeScreen extends StatefulWidget {
  const ConfigHomeScreen({
    super.key,
    required this.transport,
    required this.initialConfig,
    required this.pin,
  });

  final ConfigTransport transport;
  final HelmetConfig initialConfig;
  final String pin;

  @override
  State<ConfigHomeScreen> createState() => _ConfigHomeScreenState();
}

class _ConfigHomeScreenState extends State<ConfigHomeScreen> {
  late HelmetConfig _config;
  late TextEditingController _riderController;
  late TextEditingController _homeController;
  final _newPinController = TextEditingController();
  bool _busy = false;
  String _busyLabel = 'Working...';
  String _currentPin = '';

  @override
  void initState() {
    super.initState();
    _config = widget.initialConfig;
    _currentPin = widget.pin;
    _riderController = TextEditingController(text: _config.riderName);
    _homeController = TextEditingController(text: _config.homeBarangay);
  }

  @override
  void dispose() {
    _riderController.dispose();
    _homeController.dispose();
    _newPinController.dispose();
    widget.transport.close();
    super.dispose();
  }

  Future<void> _send(
    Map<String, dynamic> command, {
    String busyLabel = 'Working...',
  }) async {
    setState(() {
      _busy = true;
      _busyLabel = busyLabel;
    });

    final ConfigResponse response;
    try {
      response = await widget.transport.send({...command, 'pin': _currentPin});
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Request failed: $e'),
          backgroundColor: Colors.red.shade700,
        ),
      );
      return;
    }

    if (!mounted) return;
    final nextConfig = response.config;
    if (response.ok && nextConfig != null) {
      _riderController.text = nextConfig.riderName;
      _homeController.text = nextConfig.homeBarangay;
    }

    setState(() {
      _busy = false;
      if (response.ok && command['op'] == 'change_pin') {
        _currentPin = '${command['new_pin']}';
        _newPinController.clear();
      }
      if (response.ok && nextConfig != null) {
        _config = nextConfig;
      }
    });
    if (!response.ok && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(response.error),
          backgroundColor: Colors.red.shade700,
        ),
      );
    }
  }

  Future<void> _saveRider() {
    return _send({
      'op': 'set_rider',
      'rider_name': _riderController.text.trim(),
      'subject_home_barangay': _homeController.text.trim(),
    }, busyLabel: 'Saving rider info...');
  }

  Future<void> _reload() =>
      _send({'op': 'get_config'}, busyLabel: 'Reloading config...');

  Future<void> _changePin() async {
    final newPin = _newPinController.text.trim();
    if (!RegExp(r'^\d{4,12}$').hasMatch(newPin)) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('PIN must be 4-12 digits.'),
          backgroundColor: Colors.red.shade700,
        ),
      );
      return;
    }
    await _send({
      'op': 'change_pin',
      'new_pin': newPin,
    }, busyLabel: 'Changing PIN...');
  }

  Future<void> _returnToConnect() async {
    setState(() {
      _busy = true;
      _busyLabel = 'Returning to connect screen...';
    });
    await widget.transport.close();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute<void>(builder: (_) => const ConnectScreen()),
    );
  }

  Future<void> _showContactSheet({
    EmergencyContact? contact,
    int? index,
  }) async {
    final result = await showModalBottomSheet<Map<String, String>>(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xff181a20),
      builder: (_) => ContactEditorSheet(contact: contact),
    );
    if (!mounted) return;
    if (result == null) return;
    if (contact == null) {
      await _send({
        'op': 'add_contact',
        ...result,
      }, busyLabel: 'Adding contact...');
    } else {
      await _send({
        'op': 'update_contact',
        'index': index,
        ...result,
      }, busyLabel: 'Saving contact...');
    }
  }

  Future<void> _deleteContact(int index) async {
    if (_config.contacts.length <= 1) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('At least one family contact is required.'),
          backgroundColor: Colors.amber.shade800,
        ),
      );
      return;
    }

    final ok = await showDialog<bool>(
      context: context,
      builder:
          (context) => AlertDialog(
            title: const Text('Delete Contact?'),
            content: const Text(
              'This removes the contact from the helmet config.',
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('Cancel'),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(context, true),
                child: const Text('Delete'),
              ),
            ],
          ),
    );
    if (!mounted) return;
    if (ok == true) {
      await _send({
        'op': 'delete_contact',
        'index': index,
      }, busyLabel: 'Deleting contact...');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          tooltip: 'Back to connect',
          onPressed: _busy ? null : _returnToConnect,
          icon: const Icon(Icons.arrow_back),
        ),
        title: const Text('SmartShell Setup'),
        actions: [
          IconButton(
            onPressed: _busy ? null : _reload,
            icon:
                _busy
                    ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                    : const Icon(Icons.refresh),
          ),
        ],
      ),
      body: Stack(
        children: [
          SafeArea(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 760),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      StatusBanner(label: widget.transport.label),
                      const SizedBox(height: 16),
                      GlassCard(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            const SectionTitle(
                              icon: Icons.person_outline,
                              title: 'Rider Info',
                            ),
                            TextField(
                              controller: _riderController,
                              decoration: const InputDecoration(
                                labelText: 'Rider name',
                              ),
                            ),
                            const SizedBox(height: 12),
                            TextField(
                              controller: _homeController,
                              decoration: const InputDecoration(
                                labelText: 'Home barangay',
                              ),
                            ),
                            const SizedBox(height: 16),
                            FilledButton.icon(
                              onPressed: _busy ? null : _saveRider,
                              icon: const Icon(Icons.save_outlined),
                              label: const Text('Save Rider Info'),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 16),
                      GlassCard(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            const SectionTitle(
                              icon: Icons.admin_panel_settings_outlined,
                              title: 'Link Security',
                            ),
                            TextField(
                              controller: _newPinController,
                              decoration: const InputDecoration(
                                labelText: 'New helmet PIN',
                                helperText:
                                    'Use 4-12 digits. Future links require this PIN.',
                              ),
                              obscureText: true,
                              keyboardType: TextInputType.number,
                            ),
                            const SizedBox(height: 16),
                            FilledButton.icon(
                              onPressed: _busy ? null : _changePin,
                              icon: const Icon(Icons.lock_reset),
                              label: const Text('Change Link PIN'),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 16),
                      GlassCard(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Row(
                              children: [
                                const Expanded(
                                  child: SectionTitle(
                                    icon: Icons.contact_phone_outlined,
                                    title: 'Emergency Contacts',
                                  ),
                                ),
                                Text('${_config.contacts.length}/3'),
                              ],
                            ),
                            const SizedBox(height: 8),
                            if (_config.contacts.isEmpty)
                              const EmptyContactsNotice()
                            else
                              for (var i = 0; i < _config.contacts.length; i++)
                                ContactTile(
                                  contact: _config.contacts[i],
                                  onEdit:
                                      () => _showContactSheet(
                                        contact: _config.contacts[i],
                                        index: i + 1,
                                      ),
                                  onDelete:
                                      _config.contacts.length <= 1
                                          ? null
                                          : () => _deleteContact(i + 1),
                                ),
                            const SizedBox(height: 12),
                            OutlinedButton.icon(
                              onPressed:
                                  _busy || _config.contacts.length >= 3
                                      ? null
                                      : () => _showContactSheet(),
                              icon: const Icon(Icons.add),
                              label: const Text('Add Contact'),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
          if (_busy) BusyOverlay(label: _busyLabel),
        ],
      ),
    );
  }
}

class GlassCard extends StatelessWidget {
  const GlassCard({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: child,
    );
  }
}

class BusyOverlay extends StatelessWidget {
  const BusyOverlay({super.key, required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Positioned.fill(
      child: AbsorbPointer(
        child: ColoredBox(
          color: Colors.black.withValues(alpha: 0.45),
          child: Center(
            child: GlassCard(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const CircularProgressIndicator(),
                  const SizedBox(height: 16),
                  Text(label, textAlign: TextAlign.center),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class SectionTitle extends StatelessWidget {
  const SectionTitle({super.key, required this.icon, required this.title});

  final IconData icon;
  final String title;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        children: [
          Icon(icon, color: const Color(0xff60a5fa)),
          const SizedBox(width: 8),
          Text(
            title,
            style: Theme.of(
              context,
            ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
          ),
        ],
      ),
    );
  }
}

class EmptyContactsNotice extends StatelessWidget {
  const EmptyContactsNotice({super.key});

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.amber.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: Colors.amber.withValues(alpha: 0.35)),
      ),
      child: const Padding(
        padding: EdgeInsets.all(14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(Icons.info_outline, color: Colors.amber),
            SizedBox(width: 10),
            Expanded(
              child: Text(
                'At least one family contact is required before the alert system can send family SMS alerts.',
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class StatusBanner extends StatelessWidget {
  const StatusBanner({super.key, required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Color(0xff14532d), Color(0xff1d4ed8)],
        ),
        borderRadius: BorderRadius.circular(18),
      ),
      child: Row(
        children: [
          const Icon(Icons.verified, color: Colors.white),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              'Linked to $label',
              style: const TextStyle(fontWeight: FontWeight.bold),
            ),
          ),
        ],
      ),
    );
  }
}

class ContactTile extends StatelessWidget {
  const ContactTile({
    super.key,
    required this.contact,
    required this.onEdit,
    required this.onDelete,
  });

  final EmergencyContact contact;
  final VoidCallback onEdit;
  final VoidCallback? onDelete;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Colors.black.withValues(alpha: 0.22),
      child: ListTile(
        leading: CircleAvatar(child: Text('${contact.priority}')),
        title: Text(contact.name),
        subtitle: Text(contact.phone),
        trailing: Wrap(
          children: [
            IconButton(
              onPressed: onEdit,
              icon: const Icon(Icons.edit_outlined),
            ),
            if (onDelete != null)
              IconButton(
                onPressed: onDelete,
                icon: const Icon(Icons.delete_outline),
              ),
          ],
        ),
      ),
    );
  }
}

class ContactEditorSheet extends StatefulWidget {
  const ContactEditorSheet({super.key, this.contact});

  final EmergencyContact? contact;

  @override
  State<ContactEditorSheet> createState() => _ContactEditorSheetState();
}

class _ContactEditorSheetState extends State<ContactEditorSheet> {
  late final TextEditingController _nameController;
  late final TextEditingController _phoneController;

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController(text: widget.contact?.name ?? '');
    _phoneController = TextEditingController(text: widget.contact?.phone ?? '');
  }

  @override
  void dispose() {
    _nameController.dispose();
    _phoneController.dispose();
    super.dispose();
  }

  void _save() {
    Navigator.of(context).pop({
      'name': _nameController.text.trim(),
      'phone': _phoneController.text.trim(),
    });
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 20,
        bottom: MediaQuery.viewInsetsOf(context).bottom + 20,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            widget.contact == null ? 'Add Contact' : 'Edit Contact',
            style: Theme.of(
              context,
            ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _nameController,
            decoration: const InputDecoration(labelText: 'Name'),
            textInputAction: TextInputAction.next,
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _phoneController,
            decoration: const InputDecoration(labelText: 'Phone'),
            keyboardType: TextInputType.phone,
            textInputAction: TextInputAction.done,
            onSubmitted: (_) => _save(),
          ),
          const SizedBox(height: 16),
          FilledButton(onPressed: _save, child: const Text('Save')),
        ],
      ),
    );
  }
}

class ProtocolCard extends StatelessWidget {
  const ProtocolCard({super.key});

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.25),
        borderRadius: BorderRadius.circular(14),
      ),
      child: const Padding(
        padding: EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('BLE Protocol', style: TextStyle(fontWeight: FontWeight.bold)),
            SizedBox(height: 8),
            Text('Service: $serviceUuid'),
            Text('RX write: $rxUuid'),
            Text('TX notify: $txUuid'),
          ],
        ),
      ),
    );
  }
}
