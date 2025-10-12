#!/usr/bin/env python3
"""
analyze_scenario_kpis.py - Complete SUMO output analysis for both status_quo and mlh scenarios
Fixed version with correct stop counting methodology
"""

import xml.etree.ElementTree as ET
import pandas as pd
import numpy as np
import sys
import gc
import os
from datetime import datetime
from collections import defaultdict


class CompleteSUMOAnalyzer:
    def __init__(self, scenario_name, output_dir='output'):
        self.scenario = scenario_name
        self.output_dir = output_dir
        self.results = {}

        # FIXED: Actual simulation configuration based on real data
        if 'mlh' in scenario_name.lower():
            # MLH configuration - cargo bikes
            self.num_delivery_vans = 63  # Actual bike count
            self.total_packages = 917  # Actual delivery points
            self.packages_per_van = 14.6  # 917/63 average
            self.vehicle_pattern = 'cargo_bike_'
            self.vehicle_type = 'cargo_bike'
            # Vehicle dimensions for cargo bikes
            self.vehicle_length = 2.5  # meters
            self.vehicle_width = 1.0  # meters
        else:
            # Status quo configuration - delivery vans
            self.num_delivery_vans = 10  # Actual van count
            self.total_packages = 906  # Actual delivery points
            self.packages_per_van = 90.6  # 906/10 average
            self.vehicle_pattern = 'delivery_van_'
            self.vehicle_type = 'delivery_van'
            # Vehicle dimensions for vans
            self.vehicle_length = 7.5  # meters
            self.vehicle_width = 2.5  # meters

        self.vehicle_footprint = self.vehicle_length * self.vehicle_width

        # Time windows for analysis
        self.time_windows = {
            'early_morning': (0, 6),
            'morning_peak': (6, 9),
            'morning': (9, 12),
            'afternoon': (12, 15),
            'afternoon_peak': (15, 18),
            'evening_peak': (18, 21),
            'night': (21, 24)
        }

    def process_tripinfo(self):
        """Process tripinfo file - PRIMARY source for emissions and trip data"""
        file_path = f'{self.output_dir}/{self.scenario}_tripinfo.xml'
        print("\nProcessing tripinfo (primary data source)...")

        if not os.path.exists(file_path):
            print(f"  ERROR: {file_path} not found")
            return 0

        tree = ET.parse(file_path)

        delivery_trips = []
        background_trips = []
        time_window_metrics = defaultdict(lambda: defaultdict(list))

        # Track ACTUAL emissions from tripinfo
        total_network_emissions = {'CO2': 0, 'fuel': 0, 'NOx': 0, 'PMx': 0}
        delivery_emissions = {'CO2': 0, 'fuel': 0, 'NOx': 0, 'PMx': 0}

        # Track delivery vehicles
        delivery_vehicle_ids = set()
        all_vehicle_ids = set()

        for trip in tree.findall('.//tripinfo'):
            vehicle_id = trip.get('id')
            all_vehicle_ids.add(vehicle_id)

            depart = float(trip.get('depart'))
            arrival = float(trip.get('arrival'))
            duration = float(trip.get('duration'))
            distance = float(trip.get('routeLength'))
            delay = float(trip.get('timeLoss'))
            waiting = float(trip.get('waitingTime', 0))
            speed = distance / duration if duration > 0 else 0

            # Get emissions
            emissions_elem = trip.find('emissions')
            if emissions_elem is not None:
                co2 = float(emissions_elem.get('CO2_abs', 0))
                fuel = float(emissions_elem.get('fuel_abs', 0))
                nox = float(emissions_elem.get('NOx_abs', 0))
                pmx = float(emissions_elem.get('PMx_abs', 0))

                total_network_emissions['CO2'] += co2
                total_network_emissions['fuel'] += fuel
                total_network_emissions['NOx'] += nox
                total_network_emissions['PMx'] += pmx
            else:
                co2 = fuel = nox = pmx = 0

            hour = int(depart / 3600)

            # Determine time window
            time_window = 'night'
            for window_name, (start, end) in self.time_windows.items():
                if start <= hour < end:
                    time_window = window_name
                    break

            trip_data = {
                'id': vehicle_id,
                'depart': depart,
                'arrival': arrival,
                'duration': duration,
                'distance': distance,
                'delay': delay,
                'waiting': waiting,
                'speed': speed,
                'hour': hour,
                'time_window': time_window,
                'co2': co2,
                'fuel': fuel
            }

            # Identify delivery vehicles
            is_delivery = self.vehicle_pattern in vehicle_id

            if is_delivery:
                delivery_vehicle_ids.add(vehicle_id)
                delivery_trips.append(trip_data)
                time_window_metrics[time_window]['delivery_speeds'].append(speed)
                time_window_metrics[time_window]['delivery_delays'].append(delay)

                delivery_emissions['CO2'] += co2
                delivery_emissions['fuel'] += fuel
                delivery_emissions['NOx'] += nox
                delivery_emissions['PMx'] += pmx
            else:
                background_trips.append(trip_data)
                time_window_metrics[time_window]['background_speeds'].append(speed)

        print(f"  Found {len(delivery_vehicle_ids)} {self.vehicle_type}s")
        print(f"  Total vehicles: {len(all_vehicle_ids)}")

        # Convert emissions from mg to proper units
        self.results['emissions'] = {
            'total_network_vehicles': len(all_vehicle_ids),
            'total_network_CO2_kg': total_network_emissions['CO2'] / 1000000,
            'total_network_fuel_liters': total_network_emissions['fuel'] / 1000000,
            'unique_delivery_vehicles': len(delivery_vehicle_ids),
            'delivery_CO2_kg': delivery_emissions['CO2'] / 1000000,
            'delivery_fuel_liters': delivery_emissions['fuel'] / 1000000,
            'delivery_NOx_g': delivery_emissions['NOx'] / 1000,
            'delivery_PM_mg': delivery_emissions['PMx'],

            # Per package emissions
            'CO2_per_package_kg': (
                    delivery_emissions['CO2'] / 1000000 / self.total_packages) if self.total_packages > 0 else 0,
            'fuel_per_package_liters': (
                    delivery_emissions['fuel'] / 1000000 / self.total_packages) if self.total_packages > 0 else 0,
            'NOx_per_package_g': (
                    delivery_emissions['NOx'] / 1000 / self.total_packages) if self.total_packages > 0 else 0,
            'PM_per_package_mg': (delivery_emissions['PMx'] / self.total_packages) if self.total_packages > 0 else 0,

            'delivery_share_of_CO2_percent': (delivery_emissions['CO2'] / total_network_emissions['CO2'] * 100) if
            total_network_emissions['CO2'] > 0 else 0
        }

        # Calculate operational metrics
        df_delivery = pd.DataFrame(delivery_trips) if delivery_trips else pd.DataFrame()
        df_background = pd.DataFrame(background_trips) if background_trips else pd.DataFrame()

        # Time window analysis - only include windows with actual delivery activity
        time_window_results = {}
        for window in self.time_windows.keys():
            delivery_speeds = time_window_metrics[window]['delivery_speeds']
            background_speeds = time_window_metrics[window]['background_speeds']
            delivery_delays = time_window_metrics[window]['delivery_delays']

            # Only include time windows where deliveries actually occurred
            if delivery_speeds:  # Only if there's delivery data
                time_window_results[f'{window}_delivery_speed_kmh'] = np.mean(delivery_speeds) * 3.6
                time_window_results[f'{window}_delivery_delay_min'] = np.mean(delivery_delays) / 60

            # Always include background speeds for context
            if background_speeds:
                time_window_results[f'{window}_background_speed_kmh'] = np.mean(background_speeds) * 3.6

        self.results['operational'] = {
            'delivery_vehicles': len(delivery_trips),
            'background_vehicles': len(background_trips),
            'total_vehicles': len(delivery_trips) + len(background_trips),

            'delivery_total_distance_km': df_delivery['distance'].sum() / 1000 if not df_delivery.empty else 0,
            'delivery_avg_distance_km': df_delivery['distance'].mean() / 1000 if not df_delivery.empty else 0,
            'distance_per_package_km': (df_delivery[
                                            'distance'].sum() / 1000 / self.total_packages) if not df_delivery.empty and self.total_packages > 0 else 0,

            'delivery_total_time_hours': df_delivery['duration'].sum() / 3600 if not df_delivery.empty else 0,
            'delivery_avg_duration_min': df_delivery['duration'].mean() / 60 if not df_delivery.empty else 0,

            'delivery_avg_speed_kmh': df_delivery['speed'].mean() * 3.6 if not df_delivery.empty else 0,
            'background_avg_speed_kmh': df_background['speed'].mean() * 3.6 if not df_background.empty else 0,

            'delivery_total_delay_hours': df_delivery['delay'].sum() / 3600 if not df_delivery.empty else 0,
            'delivery_avg_delay_min': df_delivery['delay'].mean() / 60 if not df_delivery.empty else 0,

            'delivery_time_efficiency': 1 - (
                    df_delivery['delay'].sum() / df_delivery['duration'].sum()) if not df_delivery.empty and
                                                                                   df_delivery[
                                                                                       'duration'].sum() > 0 else 0,

            'delivery_duration_cv': (
                    df_delivery['duration'].std() / df_delivery['duration'].mean()) if not df_delivery.empty and
                                                                                       df_delivery[
                                                                                           'duration'].mean() > 0 else 0,

            **time_window_results
        }

        # Fuel efficiency
        if self.results['emissions']['delivery_fuel_liters'] > 0:
            self.results['emissions']['fuel_efficiency_km_per_liter'] = (
                    self.results['operational']['delivery_total_distance_km'] /
                    self.results['emissions']['delivery_fuel_liters']
            )
        else:
            self.results['emissions']['fuel_efficiency_km_per_liter'] = 0

        print(f"✓ Processed {len(delivery_trips)} {self.vehicle_type} trips, {len(background_trips)} background trips")
        return len(delivery_trips)

    def process_emissions_for_noise(self):
        """Extract noise levels from emissions.xml by sampling"""
        file_path = f'{self.output_dir}/{self.scenario}_emissions.xml'
        print("\nProcessing emissions for noise data (sampling)...")

        if not os.path.exists(file_path):
            print(f"  Warning: {file_path} not found - skipping noise analysis")
            self.results['emissions']['delivery_avg_noise_db'] = 0
            self.results['emissions']['background_avg_noise_db'] = 0
            self.results['emissions']['noise_per_package_db'] = 0
            return

        delivery_noise = []
        background_noise = []

        # Sample at various times of day
        sample_times = [900, 1800, 2700, 3600, 7200, 10800, 14400, 18000, 21600]

        context = ET.iterparse(file_path, events=('start', 'end'))
        context = iter(context)
        event, root = next(context)

        current_timestep = None
        vehicles_processed = 0

        for event, elem in context:
            if event == 'end':
                if elem.tag == 'timestep':
                    current_timestep = float(elem.get('time', 0))

                    # Only process selected timesteps
                    if current_timestep in sample_times:
                        print(f"  Sampling noise at time {current_timestep / 3600:.1f}h")

                        for vehicle in elem.findall('.//vehicle'):
                            vehicle_id = vehicle.get('id')
                            noise = float(vehicle.get('noise', 0))

                            if noise > 0:  # Only count vehicles that are active
                                if self.vehicle_pattern in vehicle_id:
                                    delivery_noise.append(noise)
                                else:
                                    background_noise.append(noise)

                                vehicles_processed += 1

                    # Clear processed elements to free memory
                    elem.clear()
                    root.clear()

                    # Stop if we've processed all sample times
                    if current_timestep > max(sample_times):
                        break

        # Calculate averages
        if delivery_noise:
            avg_delivery_noise = np.mean(delivery_noise)
            self.results['emissions']['delivery_avg_noise_db'] = avg_delivery_noise
            self.results['emissions']['noise_per_package_db'] = avg_delivery_noise
            print(f"  Delivery vehicle avg noise: {avg_delivery_noise:.1f} dB")
        else:
            self.results['emissions']['delivery_avg_noise_db'] = 0
            self.results['emissions']['noise_per_package_db'] = 0

        if background_noise:
            avg_background_noise = np.mean(background_noise)
            self.results['emissions']['background_avg_noise_db'] = avg_background_noise
            print(f"  Background vehicle avg noise: {avg_background_noise:.1f} dB")
        else:
            self.results['emissions']['background_avg_noise_db'] = 0

        print(f"✓ Processed noise data from {vehicles_processed} vehicle observations")

    def process_stops(self):
        """Process stop information - FIXED to count ALL stops like validation script"""
        file_path = f'{self.output_dir}/{self.scenario}_stops.xml'
        print("\nProcessing stops (using validation methodology)...")

        if not os.path.exists(file_path):
            print(f"  Warning: {file_path} not found")
            self.results['stops'] = {
                'total_delivery_stops': 0,
                'accessible_addresses': 0,
                'inaccessible_addresses': self.total_packages,
                'accessibility_rate_percent': 0
            }
            return

        tree = ET.parse(file_path)

        # FIXED: Count ALL stops, regardless of duration (matching validation script)
        delivery_stops = []
        all_delivery_stop_count = 0  # Simple counter like validation script
        stop_locations = defaultdict(int)
        vehicles_with_stops = set()
        stop_durations = []  # Track durations separately

        for stop in tree.findall('.//stopinfo'):
            vehicle_id = stop.get('id', '')

            # Check if it's a delivery vehicle
            if self.vehicle_pattern in vehicle_id:
                # COUNT EVERY STOP (matching validation script)
                all_delivery_stop_count += 1
                vehicles_with_stops.add(vehicle_id)

                started = float(stop.get('started', 0))
                ended = float(stop.get('ended', 0))
                duration = ended - started
                lane = stop.get('lane', '')
                parking = stop.get('parking', '0')

                # Store stop data for analysis (but count ALL stops)
                stop_data = {
                    'vehicle': vehicle_id,
                    'duration': duration,
                    'started': started,
                    'ended': ended,
                    'lane': lane,
                    'parking': parking == '1'
                }
                delivery_stops.append(stop_data)

                # Track durations for average calculation
                if duration > 0:
                    stop_durations.append(duration)

                edge_id = lane.rsplit('_', 1)[0] if '_' in lane else lane
                stop_locations[edge_id] += 1

        # FIXED: Use actual stop count for accessibility calculation
        accessible_addresses = all_delivery_stop_count  # Count ALL stops
        inaccessible_addresses = self.total_packages - accessible_addresses
        accessibility_rate = (accessible_addresses / self.total_packages * 100) if self.total_packages > 0 else 0

        # Calculate metrics based on stops with duration > 0
        if stop_durations:
            total_stop_duration = sum(stop_durations)
            avg_stop_duration_min = np.mean(stop_durations) / 60
        else:
            total_stop_duration = 0
            avg_stop_duration_min = 0

        total_stop_time_hours = total_stop_duration / 3600

        # Check for stop clustering
        clustered_locations = sum(1 for count in stop_locations.values() if count > 1)
        total_locations = len(stop_locations)

        self.results['stops'] = {
            'total_delivery_stops': all_delivery_stop_count,  # FIXED: actual count
            'accessible_addresses': accessible_addresses,  # FIXED: equals total stops
            'inaccessible_addresses': inaccessible_addresses,
            'accessibility_rate_percent': accessibility_rate,
            'parking_restricted_addresses': inaccessible_addresses,
            'stops_per_van': all_delivery_stop_count / self.num_delivery_vans if self.num_delivery_vans > 0 else 0,
            'avg_stop_duration_min': avg_stop_duration_min,
            'total_stop_time_hours': total_stop_time_hours,
            'stop_time_per_package_min': (
                    total_stop_duration / 60 / accessible_addresses) if accessible_addresses > 0 else 0,
            'unique_stop_locations': total_locations,
            'clustered_stop_locations': clustered_locations,
            'stop_clustering_ratio': clustered_locations / total_locations if total_locations > 0 else 0,
            'vehicles_with_stops': len(vehicles_with_stops),
            'stops_with_zero_duration': all_delivery_stop_count - len([s for s in delivery_stops if s['duration'] > 0])
        }

        # Print debugging information
        print(f"  DEBUG: Total stops in XML (all vehicles): {len(tree.findall('.//stopinfo'))}")
        print(f"  DEBUG: Delivery stops counted: {all_delivery_stop_count}")
        print(f"  DEBUG: Expected deliveries: {self.total_packages}")
        print(f"  DEBUG: Stops with zero duration: {self.results['stops']['stops_with_zero_duration']}")
        print(f"  ✅ Accessibility rate: {accessibility_rate:.1f}%")

        if accessibility_rate < 80:
            print(f"  ⚠️  Only {accessibility_rate:.1f}% of addresses accessible")
            print(f"  {inaccessible_addresses} addresses could not be served by {self.vehicle_type}s")
        else:
            print(f"  ✅ Good accessibility: {accessible_addresses} of {self.total_packages} addresses served")

        print(f"✓ Processed {all_delivery_stop_count} stops from {len(vehicles_with_stops)} {self.vehicle_type}s")

    def calculate_urban_space_metrics(self):
        """Calculate space-time occupancy and urban impact metrics"""

        # Space-time calculation
        total_stop_time_min = self.results['stops']['total_stop_time_hours'] * 60
        space_time_occupancy = total_stop_time_min * self.vehicle_footprint

        # Only calculate per-package for accessible addresses
        accessible_addresses = self.results['stops']['accessible_addresses']

        self.results['urban_space'] = {
            'vehicle_footprint_m2': self.vehicle_footprint,
            'vehicle_length_m': self.vehicle_length,
            'vehicle_width_m': self.vehicle_width,
            'total_space_time_occupancy_m2_min': space_time_occupancy,
            'space_time_per_delivery_m2_min': space_time_occupancy / accessible_addresses if accessible_addresses > 0 else 0,
            'space_time_per_package_attempted_m2_min': space_time_occupancy / self.total_packages if self.total_packages > 0 else 0,
            'avg_curbside_occupancy_min': self.results['stops']['avg_stop_duration_min']
        }

    def calculate_vehicle_utilization(self):
        """Calculate vehicle utilization metrics"""

        total_time_hours = self.results['operational']['delivery_total_time_hours']
        stop_time_hours = self.results['stops']['total_stop_time_hours']

        # Calculate actual time ratios
        if total_time_hours > 0:
            driving_time_hours = total_time_hours - stop_time_hours
            driving_ratio = driving_time_hours / total_time_hours
            stop_ratio = stop_time_hours / total_time_hours

            # Sanity check
            if stop_ratio > 0.8:  # If more than 80% is stops, flag it
                print(f"  ⚠️  High stop time ratio: {stop_ratio:.2%} - may indicate data issue or inefficiency")
        else:
            driving_ratio = 0
            stop_ratio = 0

        self.results['utilization'] = {
            'total_operation_hours': total_time_hours,
            'driving_time_hours': total_time_hours - stop_time_hours,
            'stop_time_hours': stop_time_hours,
            'driving_time_ratio': driving_ratio,
            'stop_time_ratio': stop_ratio,
            'vehicle_utilization_percent': driving_ratio * 100,
            'packages_per_hour': self.results['stops'][
                                     'accessible_addresses'] / total_time_hours if total_time_hours > 0 else 0
        }

    def process_queues_streaming(self):
        """Process queue file"""
        file_path = f'{self.output_dir}/{self.scenario}_queues.xml'

        if not os.path.exists(file_path):
            print(f"  Warning: {file_path} not found")
            self.results['congestion'] = {
                'total_queue_events': 0,
                'max_queue_length_m': 0,
                'affected_lanes': 0,
                'peak_congestion_hour': 0
            }
            return

        file_size = os.path.getsize(file_path) / (1024 ** 3)
        print(f"\nProcessing queues file ({file_size:.1f} GB)...")

        queue_stats = defaultdict(float)
        hourly_queues = defaultdict(lambda: defaultdict(float))
        affected_lanes = set()
        congestion_hotspots = defaultdict(int)

        context = ET.iterparse(file_path, events=('start', 'end'))
        context = iter(context)
        event, root = next(context)

        processed = 0
        current_time = 0

        for event, elem in context:
            if event == 'end':
                if elem.tag == 'data':
                    current_time = float(elem.get('timestep', 0))
                elif elem.tag == 'lane':
                    queue_length = float(elem.get('queueing_length', 0))
                    queue_time = float(elem.get('queueing_time', 0))

                    if queue_length > 0 or queue_time > 0:
                        processed += 1
                        lane_id = elem.get('id')
                        hour = int(current_time / 3600)

                        queue_stats['total_events'] += 1
                        queue_stats['max_queue'] = max(queue_stats['max_queue'], queue_length)
                        queue_stats['total_queue_time'] += queue_time

                        affected_lanes.add(lane_id)
                        hourly_queues[hour]['events'] += 1
                        hourly_queues[hour]['total_length'] += queue_length

                        if queue_length > 50:
                            edge_id = lane_id.split('_')[0] if '_' in lane_id else lane_id
                            if edge_id.startswith(':'):
                                edge_id = edge_id.split('_')[0]
                            congestion_hotspots[edge_id] += 1

                    elem.clear()

                if processed % 10000 == 0:
                    root.clear()
                    if processed % 100000 == 0:
                        print(f"  Processed {processed:,} queue events...")
                        if processed % 1000000 == 0:
                            gc.collect()

        peak_congestion_hour = max(
            hourly_queues.keys(),
            key=lambda h: hourly_queues[h]['events']
        ) if hourly_queues else 0

        top_hotspots = sorted(congestion_hotspots.items(), key=lambda x: x[1], reverse=True)[:10]

        self.results['congestion'] = {
            'total_queue_events': queue_stats['total_events'],
            'max_queue_length_m': queue_stats['max_queue'],
            'total_queue_time_hours': queue_stats['total_queue_time'] / 3600,
            'affected_lanes': len(affected_lanes),
            'peak_congestion_hour': peak_congestion_hour,
            'peak_hour_queue_events': hourly_queues[peak_congestion_hour]['events'] if hourly_queues else 0,
            'num_congestion_hotspots': len(congestion_hotspots),
            'worst_hotspot': top_hotspots[0][0] if top_hotspots else 'none',
            'worst_hotspot_events': top_hotspots[0][1] if top_hotspots else 0
        }

        print(f"✓ Processed {processed:,} queue events")

    def process_summary(self):
        """Process network summary file"""
        file_path = f'{self.output_dir}/{self.scenario}_summary.xml'
        print("\nProcessing network summary...")

        if not os.path.exists(file_path):
            print(f"  Warning: {file_path} not found")
            self.results['network'] = {'avg_vehicles_running': 0}
            return

        tree = ET.parse(file_path)

        time_series = []
        for step in tree.findall('.//step'):
            time = float(step.get('time'))

            running = step.get('running')
            if running is None or running == '':
                continue

            hour = int(time / 3600)

            time_window = 'night'
            for window_name, (start, end) in self.time_windows.items():
                if start <= hour < end:
                    time_window = window_name
                    break

            time_series.append({
                'time': time,
                'hour': hour,
                'time_window': time_window,
                'running': int(running),
                'waiting': int(step.get('waiting', 0)),
                'ended': int(step.get('ended', 0)),
                'mean_speed': float(step.get('meanSpeed', 0)),
                'mean_waiting_time': float(step.get('meanWaitingTime', 0))
            })

        if not time_series:
            print("  Warning: No valid timesteps found")
            self.results['network'] = {'avg_vehicles_running': 0}
            return

        df_summary = pd.DataFrame(time_series)
        df_sampled = df_summary[::60] if len(df_summary) > 60 else df_summary

        window_metrics = {}
        for window in self.time_windows.keys():
            window_data = df_sampled[df_sampled['time_window'] == window]
            if not window_data.empty:
                window_metrics[f'{window}_avg_running'] = window_data['running'].mean()
                window_metrics[f'{window}_avg_speed_kmh'] = window_data['mean_speed'].mean() * 3.6

        self.results['network'] = {
            'avg_vehicles_running': df_sampled['running'].mean(),
            'max_vehicles_running': df_sampled['running'].max(),
            'avg_network_speed_kmh': df_sampled['mean_speed'].mean() * 3.6,
            'max_network_speed_kmh': df_sampled['mean_speed'].max() * 3.6,
            'avg_waiting_vehicles': df_sampled['waiting'].mean(),
            'max_waiting_vehicles': df_sampled['waiting'].max(),
            'peak_traffic_hour': df_sampled.loc[df_sampled['running'].idxmax(), 'hour'] if not df_sampled.empty else 0,
            'peak_traffic_vehicles': df_sampled['running'].max(),
            **window_metrics
        }

        print(f"✓ Processed {len(df_summary)} time steps")

    def process_edgedata(self):
        """Process edge data"""
        file_path = f'{self.output_dir}/{self.scenario}_edgedata.xml'
        print("\nProcessing edge data...")

        if not os.path.exists(file_path):
            print(f"  Warning: {file_path} not found")
            self.results['road_performance'] = {'monitored_edges': 0}
            return

        tree = ET.parse(file_path)

        edge_metrics = []
        congested_edges = 0
        critical_edges = []

        for interval in tree.findall('.//interval'):
            for edge in interval.findall('.//edge'):
                edge_id = edge.get('id')

                metrics = {
                    'edge_id': edge_id,
                    'sampled_seconds': float(edge.get('sampledSeconds', 0)),
                    'traveltime': float(edge.get('traveltime', 0)),
                    'density': float(edge.get('density', 0)),
                    'occupancy': float(edge.get('occupancy', 0)),
                    'waiting_time': float(edge.get('waitingTime', 0)),
                    'time_loss': float(edge.get('timeLoss', 0)),
                    'speed': float(edge.get('speed', 0)),
                    'speed_relative': float(edge.get('speedRelative', 0)),
                    'departed': int(edge.get('departed', 0)),
                    'arrived': int(edge.get('arrived', 0)),
                    'entered': int(edge.get('entered', 0)),
                    'left': int(edge.get('left', 0))
                }

                edge_metrics.append(metrics)

                if metrics['occupancy'] > 25 or metrics['speed_relative'] < 0.5:
                    congested_edges += 1

                if metrics['occupancy'] > 35 or metrics['speed_relative'] < 0.3:
                    critical_edges.append({
                        'edge': edge_id,
                        'occupancy': metrics['occupancy'],
                        'speed_relative': metrics['speed_relative'],
                        'time_loss': metrics['time_loss']
                    })

        df_edges = pd.DataFrame(edge_metrics)

        if not df_edges.empty:
            critical_edges.sort(key=lambda x: x['time_loss'], reverse=True)

            self.results['road_performance'] = {
                'monitored_edges': len(edge_metrics),
                'congested_edges': congested_edges,
                'congestion_ratio': congested_edges / len(edge_metrics) if edge_metrics else 0,
                'critical_edges': len(critical_edges),
                'avg_edge_density': df_edges['density'].mean(),
                'avg_edge_occupancy': df_edges['occupancy'].mean(),
                'avg_edge_speed_kmh': df_edges['speed'].mean() * 3.6,
                'avg_relative_speed': df_edges['speed_relative'].mean(),
                'total_waiting_time_hours': df_edges['waiting_time'].sum() / 3600,
                'total_time_loss_hours': df_edges['time_loss'].sum() / 3600,
                'total_vehicles_departed': df_edges['departed'].sum(),
                'total_vehicles_arrived': df_edges['arrived'].sum(),
                'worst_edge': critical_edges[0]['edge'] if critical_edges else 'none',
                'worst_edge_occupancy': critical_edges[0]['occupancy'] if critical_edges else 0,
                'worst_edge_time_loss_hours': critical_edges[0]['time_loss'] / 3600 if critical_edges else 0,
                'p90_occupancy': df_edges['occupancy'].quantile(0.9),
                'p90_density': df_edges['density'].quantile(0.9),
                'p10_speed_relative': df_edges['speed_relative'].quantile(0.1)
            }
        else:
            self.results['road_performance'] = {'monitored_edges': 0}

        print(f"✓ Processed {len(edge_metrics)} edges")

    def process_statistics(self):
        """Process simulation statistics file"""
        file_path = f'{self.output_dir}/{self.scenario}_statistics.xml'
        print("\nProcessing simulation statistics...")

        if not os.path.exists(file_path):
            print(f"  Warning: {file_path} not found")
            self.results['simulation'] = {'vehicles_loaded': 0}
            return

        tree = ET.parse(file_path)
        root = tree.getroot()

        vehicles = root.find('.//vehicles')
        teleports = root.find('.//teleports')
        safety = root.find('.//safety')
        trip_stats = root.find('.//vehicleTripStatistics')

        self.results['simulation'] = {
            'vehicles_loaded': int(vehicles.get('loaded', 0)) if vehicles is not None else 0,
            'vehicles_inserted': int(vehicles.get('inserted', 0)) if vehicles is not None else 0,
            'vehicles_running': int(vehicles.get('running', 0)) if vehicles is not None else 0,
            'vehicles_waiting': int(vehicles.get('waiting', 0)) if vehicles is not None else 0,
            'teleports_total': int(teleports.get('total', 0)) if teleports is not None else 0,
            'teleports_jam': int(teleports.get('jam', 0)) if teleports is not None else 0,
            'collisions': int(safety.get('collisions', 0)) if safety is not None else 0,
            'emergency_stops': int(safety.get('emergencyStops', 0)) if safety is not None else 0,
            'avg_route_length_m': float(trip_stats.get('routeLength', 0)) if trip_stats is not None else 0,
            'avg_speed_ms': float(trip_stats.get('speed', 0)) if trip_stats is not None else 0,
            'avg_duration_s': float(trip_stats.get('duration', 0)) if trip_stats is not None else 0,
            'avg_waiting_time_s': float(trip_stats.get('waitingTime', 0)) if trip_stats is not None else 0,
            'avg_time_loss_s': float(trip_stats.get('timeLoss', 0)) if trip_stats is not None else 0
        }

        if self.results['simulation']['vehicles_inserted'] > 0:
            self.results['simulation']['teleport_rate'] = (
                    self.results['simulation']['teleports_total'] /
                    self.results['simulation']['vehicles_inserted'] * 100
            )
        else:
            self.results['simulation']['teleport_rate'] = 0

        print("✓ Processed simulation statistics")

    def calculate_economic_kpis(self):
        """Calculate economic metrics with researched German market data"""

        # Based on actual German delivery driver wages and fuel costs (2024)
        ASSUMPTIONS = {
            'driver_cost_per_hour': 16,  # EUR - German median hourly wage for delivery drivers
            'fuel_cost_per_liter': 1.58,  # EUR - Munich diesel price 2024
            'van_fixed_cost_per_day': 50,  # EUR - leasing + insurance
            'van_cost_per_km': 0.30,  # EUR - maintenance + depreciation
            'bike_fixed_cost_per_day': 20,  # EUR - lower than van
            'bike_cost_per_km': 0.10,  # EUR - much lower maintenance
            'package_revenue': 7.50,  # EUR per package
            'carbon_tax_per_ton': 50,  # EUR per ton CO2
            'electricity_cost_per_kwh': 0.30  # EUR for e-bikes
        }

        if 'mlh' in self.scenario.lower():
            # MLH economic model
            labor_cost = self.results['operational']['delivery_total_time_hours'] * ASSUMPTIONS['driver_cost_per_hour']
            distance_cost = self.results['operational']['delivery_total_distance_km'] * ASSUMPTIONS['bike_cost_per_km']
            fixed_cost = self.num_delivery_vans * ASSUMPTIONS['bike_fixed_cost_per_day']
            energy_cost = 0  # Negligible for e-bikes
            carbon_cost = 0  # Zero emissions for e-bikes

            total_cost = labor_cost + distance_cost + fixed_cost
            total_revenue = self.results['stops']['accessible_addresses'] * ASSUMPTIONS['package_revenue']

            self.results['economic'] = {
                'assumptions_documented': 'Based on German market research 2024',
                'labor_cost_eur': labor_cost,
                'energy_cost_eur': energy_cost,
                'distance_cost_eur': distance_cost,
                'fixed_cost_eur': fixed_cost,
                'carbon_tax_eur': carbon_cost,
                'total_cost_eur': total_cost,
                'cost_per_accessible_address_eur': total_cost / self.results['stops']['accessible_addresses'] if
                self.results['stops']['accessible_addresses'] > 0 else 0,
                'total_revenue_eur': total_revenue,
                'gross_profit_eur': total_revenue - total_cost,
                'profit_margin_percent': (
                        (total_revenue - total_cost) / total_revenue * 100) if total_revenue > 0 else 0
            }
        else:
            # Status quo van model
            labor_cost = self.results['operational']['delivery_total_time_hours'] * ASSUMPTIONS['driver_cost_per_hour']
            fuel_cost = self.results['emissions']['delivery_fuel_liters'] * ASSUMPTIONS['fuel_cost_per_liter']
            distance_cost = self.results['operational']['delivery_total_distance_km'] * ASSUMPTIONS['van_cost_per_km']
            fixed_cost = self.num_delivery_vans * ASSUMPTIONS['van_fixed_cost_per_day']

            # Environmental costs
            carbon_cost = (self.results['emissions']['delivery_CO2_kg'] / 1000) * ASSUMPTIONS['carbon_tax_per_ton']

            total_cost = labor_cost + fuel_cost + distance_cost + fixed_cost + carbon_cost
            total_revenue = self.results['stops']['accessible_addresses'] * ASSUMPTIONS['package_revenue']

            self.results['economic'] = {
                'assumptions_documented': 'Based on German market research 2024',
                'labor_cost_eur': labor_cost,
                'fuel_cost_eur': fuel_cost,
                'distance_cost_eur': distance_cost,
                'fixed_cost_eur': fixed_cost,
                'carbon_tax_eur': carbon_cost,
                'total_cost_eur': total_cost,
                'cost_per_accessible_address_eur': total_cost / self.results['stops']['accessible_addresses'] if
                self.results['stops']['accessible_addresses'] > 0 else 0,
                'total_revenue_eur': total_revenue,
                'gross_profit_eur': total_revenue - total_cost,
                'profit_margin_percent': (
                        (total_revenue - total_cost) / total_revenue * 100) if total_revenue > 0 else 0
            }

    def calculate_service_quality_kpis(self):
        """Calculate service quality metrics"""

        accessible = self.results['stops']['accessible_addresses']

        self.results['service'] = {
            'total_packages_attempted': self.total_packages,
            'packages_delivered': accessible,
            'packages_undeliverable': self.results['stops']['inaccessible_addresses'],
            'service_coverage_percent': self.results['stops']['accessibility_rate_percent'],
            'packages_per_stop': accessible / self.results['stops']['total_delivery_stops'] if self.results['stops'][
                                                                                                   'total_delivery_stops'] > 0 else 0,
            'delivery_density_per_km': accessible / self.results['operational']['delivery_total_distance_km'] if
            self.results['operational']['delivery_total_distance_km'] > 0 else 0,
            'delivery_time_reliability': 1 - self.results['operational'].get('delivery_duration_cv', 0),
            'delivery_time_efficiency': self.results['operational']['delivery_time_efficiency']
        }

    def calculate_comparison_metrics(self):
        """Calculate key metrics for scenario comparison"""

        # Core comparison metrics
        self.results['comparison'] = {
            # Accessibility
            'addresses_accessible_percent': self.results['stops']['accessibility_rate_percent'],
            'parking_restricted_percent': (self.results['stops'][
                                               'inaccessible_addresses'] / self.total_packages * 100) if self.total_packages > 0 else 0,

            # Environmental
            'co2_per_accessible_address_kg': self.results['emissions']['delivery_CO2_kg'] / self.results['stops'][
                'accessible_addresses'] if self.results['stops']['accessible_addresses'] > 0 else 0,
            'noise_level_db': self.results['emissions']['delivery_avg_noise_db'],

            # Operational
            'vehicles_required': self.num_delivery_vans,
            'avg_speed_kmh': self.results['operational']['delivery_avg_speed_kmh'],
            'distance_per_package_km': self.results['operational']['distance_per_package_km'],

            # Urban impact
            'space_time_per_delivery_m2_min': self.results['urban_space']['space_time_per_delivery_m2_min'],
            'vehicle_footprint_m2': self.vehicle_footprint,

            # Economic
            'cost_per_accessible_address_eur': self.results['economic']['cost_per_accessible_address_eur'],

            # Network
            'delivery_vehicles_percent_of_traffic': (
                    self.num_delivery_vans / self.results['emissions']['total_network_vehicles'] * 100) if
            self.results['emissions']['total_network_vehicles'] > 0 else 0
        }

    def generate_comprehensive_report(self):
        """Generate detailed KPI report with correct fleet information"""
        print("\n" + "=" * 80)
        print(f"COMPREHENSIVE KPI REPORT - {self.scenario.upper()}")
        print("=" * 80)

        vehicle_label = "cargo bikes" if 'mlh' in self.scenario.lower() else "vans"

        print("\n🎯 KEY FINDING - SERVICE ACCESSIBILITY:")
        print(f"  ✅ {self.results['stops']['accessibility_rate_percent']:.1f}% of addresses accessible")
        print(f"  {self.results['stops']['accessible_addresses']} of {self.total_packages} packages delivered")
        if self.results['stops']['inaccessible_addresses'] > 0:
            print(f"  {self.results['stops']['inaccessible_addresses']} addresses could not be reached")

        print("\n📊 OPERATIONAL PERFORMANCE:")
        print(
            f"  Fleet: {self.num_delivery_vans} {vehicle_label} × {self.packages_per_van:.1f} packages = {self.total_packages} total")
        print(f"  Total distance: {self.results['operational']['delivery_total_distance_km']:.1f} km")
        print(f"  Distance per package: {self.results['operational']['distance_per_package_km']:.2f} km")
        print(f"  Avg speed: {self.results['operational']['delivery_avg_speed_kmh']:.1f} km/h")
        print(f"  Time efficiency: {self.results['operational']['delivery_time_efficiency'] * 100:.1f}%")

        print("\n🌱 ENVIRONMENTAL IMPACT:")
        print(f"  Total CO2: {self.results['emissions']['delivery_CO2_kg']:.1f} kg")
        print(f"  CO2 per delivered package: {self.results['comparison']['co2_per_accessible_address_kg']:.3f} kg")
        print(f"  Average noise: {self.results['emissions']['delivery_avg_noise_db']:.1f} dB")
        if 'status_quo' in self.scenario:
            print(f"  Fuel efficiency: {self.results['emissions']['fuel_efficiency_km_per_liter']:.2f} km/L")

        print("\n🏙️ URBAN SPACE IMPACT:")
        print(f"  Vehicle footprint: {self.vehicle_footprint:.1f} m²")
        print(f"  Space-time per delivery: {self.results['urban_space']['space_time_per_delivery_m2_min']:.1f} m²·min")
        print(f"  Total space-time: {self.results['urban_space']['total_space_time_occupancy_m2_min']:.0f} m²·min")

        print("\n🚗 VEHICLE UTILIZATION:")
        print(f"  Driving time: {self.results['utilization']['driving_time_ratio'] * 100:.1f}%")
        print(f"  Stop time: {self.results['utilization']['stop_time_ratio'] * 100:.1f}%")
        print(f"  Packages per hour: {self.results['utilization']['packages_per_hour']:.1f}")

        print("\n💰 ECONOMIC PERFORMANCE:")
        print(f"  Total cost: €{self.results['economic']['total_cost_eur']:.2f}")
        print(f"  Cost per accessible address: €{self.results['economic']['cost_per_accessible_address_eur']:.2f}")

        print("\n🚦 NETWORK IMPACT:")
        print(
            f"  Delivery vehicles as % of traffic: {self.results['comparison']['delivery_vehicles_percent_of_traffic']:.3f}%")
        print(f"  Queue events: {self.results['congestion']['total_queue_events']:,.0f}")
        print(
            f"  Congested edges: {self.results['road_performance']['congested_edges']} ({self.results['road_performance']['congestion_ratio'] * 100:.1f}%)")

        self.save_comprehensive_results()

        print("\n" + "=" * 80)
        print(f"✅ Analysis complete! Results saved to {self.scenario}_complete_kpis.csv")
        print("=" * 80)

    def save_comprehensive_results(self):
        """Save all results to CSV and text report"""
        flat_results = {}
        for category, metrics in self.results.items():
            if isinstance(metrics, dict):
                for metric, value in metrics.items():
                    flat_results[f"{category}_{metric}"] = value

        flat_results['scenario'] = self.scenario
        flat_results['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        df = pd.DataFrame([flat_results])
        filename = f'{self.scenario}_complete_kpis.csv'
        df.to_csv(filename, index=False)

        with open(f'{self.scenario}_detailed_report.txt', 'w') as f:
            f.write(f"Detailed KPI Report for {self.scenario}\n")
            f.write("=" * 80 + "\n\n")
            f.write("KEY FINDINGS:\n")
            f.write("-" * 40 + "\n")
            f.write(f"Service Accessibility: {self.results['stops']['accessibility_rate_percent']:.1f}%\n")
            f.write(f"Accessible Addresses: {self.results['stops']['accessible_addresses']}\n")
            f.write(f"Inaccessible Addresses: {self.results['stops']['inaccessible_addresses']}\n")
            f.write(
                f"CO2 per Accessible Address: {self.results['comparison']['co2_per_accessible_address_kg']:.3f} kg\n")
            f.write(f"Vehicle Footprint: {self.vehicle_footprint} m²\n")
            f.write(
                f"Delivery Vehicles % of Traffic: {self.results['comparison']['delivery_vehicles_percent_of_traffic']:.3f}%\n")
            f.write("\n")

            for category, metrics in self.results.items():
                f.write(f"\n{category.upper()}:\n")
                f.write("-" * 40 + "\n")
                if isinstance(metrics, dict):
                    for metric, value in metrics.items():
                        f.write(f"  {metric}: {value}\n")

    def run(self):
        """Run complete analysis pipeline"""
        print(f"\nStarting COMPLETE analysis for {self.scenario}...")
        print("=" * 80)

        try:
            # Process tripinfo first (primary data source)
            self.process_tripinfo()

            # Process emissions for noise data
            self.process_emissions_for_noise()
            gc.collect()

            # Process other files
            self.process_stops()
            self.process_queues_streaming()
            gc.collect()

            self.process_summary()
            self.process_edgedata()
            self.process_statistics()

            # Calculate derived metrics
            self.calculate_urban_space_metrics()
            self.calculate_vehicle_utilization()
            self.calculate_economic_kpis()
            self.calculate_service_quality_kpis()
            self.calculate_comparison_metrics()

            # Generate report
            self.generate_comprehensive_report()

            return self.results

        except Exception as e:
            print(f"\n❌ Error during analysis: {e}")
            import traceback
            traceback.print_exc()
            return None


if __name__ == "__main__":
    scenario = sys.argv[1] if len(sys.argv) > 1 else 'status_quo'

    analyzer = CompleteSUMOAnalyzer(scenario)
    results = analyzer.run()

    if results:
        print(f"\n🎉 SUCCESS! Complete analysis finished for {scenario}")
        print(f"📊 Check {scenario}_complete_kpis.csv for all metrics")
        print(f"📝 Check {scenario}_detailed_report.txt for detailed breakdown")